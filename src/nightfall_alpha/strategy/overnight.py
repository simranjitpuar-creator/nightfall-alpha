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
    frames: list[pd.DataFrame] = []

    for _, group in clean.groupby("symbol", sort=False):
        symbol_frame = group.sort_values("date").copy()
        previous_close = symbol_frame["close"].shift(1)
        symbol_frame["overnight_return"] = symbol_frame["open"] / previous_close - 1.0
        symbol_frame["intraday_return"] = symbol_frame["close"] / symbol_frame["open"] - 1.0
        symbol_frame["close_to_close_return"] = symbol_frame["close"] / previous_close - 1.0
        symbol_frame["next_overnight_return"] = symbol_frame["overnight_return"].shift(-1)
        symbol_frame["exit_date"] = symbol_frame["date"].shift(-1)

        rolling = symbol_frame["overnight_return"].rolling(lookback_days, min_periods=min_history)
        symbol_frame["overnight_mean"] = rolling.mean()
        symbol_frame["overnight_vol"] = rolling.std(ddof=0)
        symbol_frame["overnight_sharpe"] = np.where(
            symbol_frame["overnight_vol"] > 0,
            symbol_frame["overnight_mean"] / symbol_frame["overnight_vol"] * np.sqrt(252.0),
            np.nan,
        )
        symbol_frame["overnight_win_rate"] = (
            symbol_frame["overnight_return"].gt(0).rolling(lookback_days, min_periods=min_history).mean()
        )
        frames.append(symbol_frame)

    if not frames:
        return pd.DataFrame()

    features = pd.concat(frames, ignore_index=True)
    return features.sort_values(["date", "symbol"]).reset_index(drop=True)


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


def generate_signals(prices: pd.DataFrame, config: OvernightEffectConfig | None = None) -> pd.DataFrame:
    cfg = config or OvernightEffectConfig()
    features = build_overnight_features(prices, cfg.lookback_days, cfg.min_history)
    if features.empty:
        return pd.DataFrame()

    candidates = features.dropna(subset=["overnight_sharpe", "next_overnight_return", "exit_date"]).copy()
    candidates = candidates[candidates["overnight_sharpe"] >= cfg.min_signal]
    rows: list[pd.DataFrame] = []

    for date, date_frame in candidates.groupby("date", sort=True):
        selected = date_frame.nlargest(cfg.top_n, "overnight_sharpe").copy()
        if selected.empty:
            continue

        if cfg.allocation == "equal":
            raw_scores = np.ones(len(selected), dtype=float)
        else:
            raw_scores = selected["overnight_sharpe"].clip(lower=0.0).to_numpy(dtype=float)
            if raw_scores.sum() <= 0:
                raw_scores = np.ones(len(selected), dtype=float)

        selected["weight"] = _project_capped_simplex(raw_scores, cfg.max_weight)
        selected["signal_rank"] = np.arange(1, len(selected) + 1)
        selected["signal_date"] = date
        rows.append(
            selected[
                [
                    "signal_date",
                    "exit_date",
                    "symbol",
                    "weight",
                    "overnight_sharpe",
                    "overnight_mean",
                    "overnight_vol",
                    "overnight_win_rate",
                    "next_overnight_return",
                    "signal_rank",
                ]
            ]
        )

    if not rows:
        return pd.DataFrame(
            columns=[
                "signal_date",
                "exit_date",
                "symbol",
                "weight",
                "overnight_sharpe",
                "overnight_mean",
                "overnight_vol",
                "overnight_win_rate",
                "next_overnight_return",
                "signal_rank",
            ]
        )

    signals = pd.concat(rows, ignore_index=True)
    return signals.sort_values(["signal_date", "signal_rank"]).reset_index(drop=True)
