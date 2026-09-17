from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from nightfall_alpha.data.schema import validate_prices_frame


@dataclass(frozen=True)
class OvernightEffectConfig:
    lookback_days: int = 63
    min_history: int = 40
    top_n: int = 25
    max_weight: float = 0.07
    min_signal: float = 0.0
    allocation: str = "score"


def build_overnight_features(prices: pd.DataFrame, lookback_days: int = 63, min_history: int = 40) -> pd.DataFrame:
    clean = validate_prices_frame(prices)
    if clean.empty:
        return pd.DataFrame()

    # Vectorized per-symbol calculations (C-level groupby ops, no Python loops).
    grouped = clean.groupby("symbol", sort=False)
    previous_close = grouped["close"].shift(1)
    clean["overnight_return"] = clean["open"] / previous_close - 1.0
    clean["intraday_return"] = clean["close"] / clean["open"] - 1.0
    clean["close_to_close_return"] = clean["close"] / previous_close - 1.0
    clean["next_overnight_return"] = grouped["overnight_return"].shift(-1)
    clean["exit_date"] = grouped["date"].shift(-1)

    # Cumsum-based rolling stats. groupby().rolling() materializes a MultiIndex
    # per group and is the dominant cost on multi-million-row frames; rolling
    # sums via per-group cumsum + shift are pure C-level arithmetic instead.
    symbols = clean["symbol"]
    ret = clean["overnight_return"]
    valid = ret.notna().astype(float)
    x = ret.fillna(0.0)

    cum_sum = x.groupby(symbols, sort=False).cumsum()
    cum_sum2 = (x * x).groupby(symbols, sort=False).cumsum()
    cum_valid = valid.groupby(symbols, sort=False).cumsum()
    cum_rows = valid.groupby(symbols, sort=False).cumcount() + 1.0

    def _roll(cum: pd.Series) -> pd.Series:
        return cum - cum.groupby(symbols, sort=False).shift(lookback_days).fillna(0.0)

    roll_sum = _roll(cum_sum)
    roll_sum2 = _roll(cum_sum2)
    roll_valid = _roll(cum_valid)
    roll_rows = np.minimum(cum_rows, float(lookback_days))

    enough = roll_valid >= float(min_history)
    mean = roll_sum / roll_valid.replace(0.0, np.nan)
    variance = (roll_sum2 / roll_valid.replace(0.0, np.nan) - mean * mean).clip(lower=0.0)
    clean["overnight_mean"] = mean.where(enough)
    clean["overnight_vol"] = np.sqrt(variance).where(enough)
    clean["overnight_sharpe"] = np.where(
        clean["overnight_vol"] > 0,
        clean["overnight_mean"] / clean["overnight_vol"] * np.sqrt(252.0),
        np.nan,
    )

    # Win rate: NaN overnight returns count as non-wins inside the window
    # (matches the previous rolling-mean-of-indicator behaviour).
    win = ret.gt(0).astype(float)
    cum_win = win.groupby(symbols, sort=False).cumsum()
    roll_win = _roll(cum_win)
    clean["overnight_win_rate"] = (roll_win / roll_rows).where(roll_rows >= float(min_history))

    # Rolling median cannot use cumsums; a plain per-symbol Series.rolling loop
    # avoids the groupby.rolling MultiIndex overhead and is fast enough.
    clean["dollar_volume"] = clean["close"] * clean["volume"]
    adv = pd.Series(np.nan, index=clean.index, dtype=float)
    dollar_volume = clean["dollar_volume"]
    for idx in symbols.groupby(symbols, sort=False).indices.values():
        adv.iloc[idx] = dollar_volume.iloc[idx].rolling(20, min_periods=5).median().to_numpy()
    clean["adv_dollars"] = adv

    return clean.sort_values(["date", "symbol"]).reset_index(drop=True)


def _project_capped_simplex(values: np.ndarray, max_weight: float) -> np.ndarray:
    values = np.clip(np.asarray(values, dtype=float), 0.0, None)
    if values.sum() <= 0:
        return np.zeros_like(values)

    cap = max(0.0, float(max_weight))
    if cap <= 0:
        return np.zeros_like(values)

    target_sum = min(1.0, cap * len(values))
    weights = values / values.sum() * target_sum

    fixed = np.zeros(len(values), dtype=bool)
    for _ in range(len(values) + 1):
        over = (weights > cap + 1e-12) & ~fixed
        if not over.any():
            break
        fixed |= over
        weights[fixed] = cap
        remaining = target_sum - weights[fixed].sum()
        if remaining <= 0:
            weights[~fixed] = 0.0
            break
        free = ~fixed
        free_values = values[free]
        if free_values.sum() <= 0:
            weights[free] = remaining / free.sum()
        else:
            weights[free] = free_values / free_values.sum() * remaining

    return np.clip(weights, 0.0, cap)


SIGNAL_OUTPUT_COLUMNS = [
    "signal_date",
    "exit_date",
    "symbol",
    "weight",
    "overnight_sharpe",
    "overnight_mean",
    "overnight_vol",
    "overnight_win_rate",
    "adv_dollars",
    "next_overnight_return",
    "signal_rank",
]


def signals_from_features(features: pd.DataFrame, config: OvernightEffectConfig | None = None) -> pd.DataFrame:
    """Select and weight positions from a pre-computed feature frame."""
    cfg = config or OvernightEffectConfig()
    if features.empty:
        return pd.DataFrame(columns=SIGNAL_OUTPUT_COLUMNS)

    candidates = features.dropna(subset=["overnight_sharpe", "next_overnight_return", "exit_date"])
    candidates = candidates[candidates["overnight_sharpe"] >= cfg.min_signal]
    if candidates.empty:
        return pd.DataFrame(columns=SIGNAL_OUTPUT_COLUMNS)

    # Vectorized top-N per date: rank within each date instead of a Python
    # nlargest loop over thousands of per-date frames.
    rank = candidates.groupby("date", sort=True)["overnight_sharpe"].rank(method="first", ascending=False)
    selected = candidates[rank <= cfg.top_n].copy().reset_index(drop=True)
    selected["signal_rank"] = rank[rank <= cfg.top_n].to_numpy(dtype=int)
    selected["signal_date"] = selected["date"]

    if cfg.allocation == "equal":
        scores = pd.Series(1.0, index=selected.index)
    else:
        scores = selected["overnight_sharpe"].clip(lower=0.0)
        score_sums = scores.groupby(selected["date"], sort=False).transform("sum")
        scores = scores.where(score_sums > 0, 1.0)

    # The capped-simplex projection is iterative, but each date holds at most
    # top_n names, so a lightweight per-date numpy loop is cheap.
    score_values = scores.to_numpy(dtype=float)
    weights = np.zeros(len(selected), dtype=float)
    for idx in selected.groupby("date", sort=False).indices.values():
        weights[idx] = _project_capped_simplex(score_values[idx], cfg.max_weight)
    selected["weight"] = weights

    signals = selected[SIGNAL_OUTPUT_COLUMNS]
    return signals.sort_values(["signal_date", "signal_rank"]).reset_index(drop=True)


def generate_signals(prices: pd.DataFrame, config: OvernightEffectConfig | None = None) -> pd.DataFrame:
    cfg = config or OvernightEffectConfig()
    features = build_overnight_features(prices, cfg.lookback_days, cfg.min_history)
    return signals_from_features(features, cfg)
