"""Walk-forward / out-of-sample evaluation for the overnight strategy.

Instead of ranking parameters on the full sample (in-sample), the data is
split into rolling folds: parameters are selected on a training window and
then frozen for the following out-of-sample test window. The stitched OOS
segments give an honest, dynamically re-fit equity curve that adapts as the
market moves through time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import product

import numpy as np
import pandas as pd

from nightfall_alpha.backtest.engine import BacktestConfig, run_overnight_backtest
from nightfall_alpha.backtest.metrics import performance_metrics
from nightfall_alpha.strategy.overnight import (
    OvernightEffectConfig,
    build_overnight_features,
    signals_from_features,
)

SELECTION_METRICS = {"sharpe", "sortino", "calmar", "cagr"}


@dataclass(frozen=True)
class WalkForwardConfig:
    train_days: int = 756
    test_days: int = 63
    step_days: int = 63
    lookback_grid: tuple[int, ...] = (42, 63, 126)
    top_n_grid: tuple[int, ...] = (15, 25, 40)
    min_signal_grid: tuple[float, ...] = (0.0,)
    selection_metric: str = "sharpe"
    start_date: str | None = None  # ignore folds whose test window ends before this
    max_folds: int | None = None  # keep only the most recent N folds
    base_max_weight: float = 0.07
    min_history_ratio: float = 0.63  # min_history = int(lookback * ratio), matching 40/63 default

    def parameter_grid(self) -> list[OvernightEffectConfig]:
        combos: list[OvernightEffectConfig] = []
        for lookback, top_n, min_signal in product(self.lookback_grid, self.top_n_grid, self.min_signal_grid):
            combos.append(
                OvernightEffectConfig(
                    lookback_days=int(lookback),
                    min_history=max(5, int(int(lookback) * self.min_history_ratio)),
                    top_n=int(top_n),
                    max_weight=float(self.base_max_weight),
                    min_signal=float(min_signal),
                )
            )
        return combos


@dataclass(frozen=True)
class WalkForwardResult:
    folds: pd.DataFrame
    oos_daily: pd.DataFrame
    oos_metrics: dict[str, object]
    in_sample_average_sharpe: float | None
    config: WalkForwardConfig = field(default_factory=WalkForwardConfig)


def _fold_windows(dates: pd.DatetimeIndex, cfg: WalkForwardConfig) -> list[tuple[pd.Timestamp, ...]]:
    windows: list[tuple[pd.Timestamp, ...]] = []
    start = 0
    n = len(dates)
    while start + cfg.train_days < n:
        train_end_idx = start + cfg.train_days
        test_end_idx = min(train_end_idx + cfg.test_days, n)
        windows.append(
            (dates[start], dates[train_end_idx - 1], dates[train_end_idx], dates[test_end_idx - 1])
        )
        start += cfg.step_days
    return windows


def _metrics_sharpe(metrics: dict[str, object]) -> float:
    value = metrics.get("sharpe")
    return float(value) if value is not None else float("-inf")


def run_walk_forward(
    prices: pd.DataFrame,
    wf_config: WalkForwardConfig | None = None,
    backtest_config: BacktestConfig | None = None,
    *,
    risk_free_rate: float = 0.0,
    initial_capital: float = 1_000_000.0,
) -> WalkForwardResult:
    cfg = wf_config or WalkForwardConfig()
    bt_cfg = backtest_config or BacktestConfig(initial_capital=initial_capital)
    if cfg.selection_metric not in SELECTION_METRICS:
        raise ValueError(f"selection_metric must be one of {sorted(SELECTION_METRICS)}")

    clean = prices.copy()
    clean["date"] = pd.to_datetime(clean["date"]).dt.normalize()
    dates = pd.DatetimeIndex(sorted(clean["date"].unique()))

    windows = _fold_windows(dates, cfg)
    if cfg.start_date:
        cutoff = pd.Timestamp(cfg.start_date)
        windows = [w for w in windows if w[3] >= cutoff]
    if cfg.max_folds:
        windows = windows[-int(cfg.max_folds):]
    if not windows:
        raise ValueError("Not enough price history for the requested walk-forward windows.")

    # Feature computation only needs history back to the first training window
    # (plus the longest rolling lookback as a warm-up buffer).
    max_lookback = max(int(lookback) for lookback in cfg.lookback_grid)
    first_train_start = windows[0][0]
    buffer_days = int(max_lookback * 2)
    earliest_needed = first_train_start - pd.Timedelta(days=buffer_days)
    clean = clean[clean["date"] >= earliest_needed].copy()

    grid = cfg.parameter_grid()
    feature_cache: dict[tuple[int, int], pd.DataFrame] = {}

    def features_for(config: OvernightEffectConfig, upto: pd.Timestamp) -> pd.DataFrame:
        key = (config.lookback_days, config.min_history)
        cached = feature_cache.get(key)
        if cached is None:
            cached = build_overnight_features(clean, config.lookback_days, config.min_history)
            feature_cache[key] = cached
        return cached[cached["date"] <= upto]

    fold_rows: list[dict[str, object]] = []
    oos_parts: list[pd.DataFrame] = []

    for fold_number, (train_start, train_end, test_start, test_end) in enumerate(windows, start=1):
        best_config: OvernightEffectConfig | None = None
        best_score = float("-inf")
        for candidate in grid:
            train_features = features_for(candidate, train_end)
            train_features = train_features[train_features["date"] >= train_start]
            signals = signals_from_features(train_features, candidate)
            if signals.empty:
                continue
            result = run_overnight_backtest(signals, bt_cfg)
            metrics = performance_metrics(
                result.daily, initial_capital=bt_cfg.initial_capital, risk_free_rate=risk_free_rate
            )
            score = metrics.get(cfg.selection_metric)
            score = float(score) if score is not None else float("-inf")
            if best_config is None or score > best_score:
                best_score = score
                best_config = candidate

        if best_config is None:
            continue

        test_features = features_for(best_config, test_end)
        test_features = test_features[
            (test_features["date"] >= test_start) & (test_features["date"] <= test_end)
        ]
        oos_signals = signals_from_features(test_features, best_config)
        if oos_signals.empty:
            continue
        oos_result = run_overnight_backtest(oos_signals, bt_cfg)
        oos_metrics = performance_metrics(
            oos_result.daily, initial_capital=bt_cfg.initial_capital, risk_free_rate=risk_free_rate
        )
        oos_parts.append(oos_result.daily)

        fold_rows.append(
            {
                "fold": fold_number,
                "train_start": train_start.strftime("%Y-%m-%d"),
                "train_end": train_end.strftime("%Y-%m-%d"),
                "test_start": test_start.strftime("%Y-%m-%d"),
                "test_end": test_end.strftime("%Y-%m-%d"),
                "lookback_days": best_config.lookback_days,
                "top_n": best_config.top_n,
                "min_signal": best_config.min_signal,
                "train_metric": best_score,
                "oos_sharpe": oos_metrics.get("sharpe"),
                "oos_cagr": oos_metrics.get("cagr"),
                "oos_max_drawdown": oos_metrics.get("max_drawdown"),
                "oos_days": oos_metrics.get("observations"),
            }
        )

    folds = pd.DataFrame(fold_rows)
    if oos_parts:
        oos_daily = pd.concat(oos_parts, ignore_index=True).sort_values("signal_date").reset_index(drop=True)
        # Rebuild a compounded equity path across stitched OOS segments.
        equity = float(initial_capital)
        compounded: list[float] = []
        for net in pd.to_numeric(oos_daily["net_return"], errors="coerce").fillna(0.0):
            equity *= 1.0 + float(net)
            compounded.append(equity)
        oos_daily["starting_equity"] = [initial_capital] + compounded[:-1]
        oos_daily["ending_equity"] = compounded
        oos_metrics_all = performance_metrics(
            oos_daily, initial_capital=initial_capital, risk_free_rate=risk_free_rate
        )
    else:
        oos_daily = pd.DataFrame()
        oos_metrics_all = {}

    train_sharpes = pd.to_numeric(folds["train_metric"], errors="coerce") if not folds.empty else pd.Series(dtype=float)
    finite = train_sharpes[np.isfinite(train_sharpes)] if len(train_sharpes) else train_sharpes
    in_sample_avg = float(finite.mean()) if len(finite) else None

    return WalkForwardResult(
        folds=folds,
        oos_daily=oos_daily,
        oos_metrics=oos_metrics_all,
        in_sample_average_sharpe=in_sample_avg,
        config=cfg,
    )
