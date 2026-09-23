"""Daily signal-selection + daily optimizer-allocation backtest.

This is the hybrid of the two existing research modes:

- The signal backtest re-ranks the universe every day and sizes the top-N
  book by signal score (capped simplex).
- The portfolio suites hold a fixed basket and only decide weights, once
  (static) or at a chosen rebalance frequency.

Here the universe is re-ranked every day exactly like the signal backtest,
but the nightly book is sized by a portfolio optimizer (mean-variance,
minimum-variance, ...) estimated on the trailing overnight-return window of
that night's candidates only. Membership changes daily, weights change daily,
and every weight change is billed at each stock's own cost rate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from nightfall_alpha.backtest.metrics import performance_metrics
from nightfall_alpha.portfolio.optimizers import (
    _per_stock_cost_rates,
    inverse_volatility_weights,
    kelly_weights,
    mean_variance_weights,
    min_cvar_weights,
    minimum_variance_weights,
    project_capped_simplex,
)
from nightfall_alpha.strategy.overnight import build_overnight_features

OPTIMIZER_METHODS: dict[str, str] = {
    "score_weighted": "Signal Score Weighted (baseline)",
    "equal_weight": "Equal Weight",
    "kelly": "Kelly 50%",
    "mean_variance": "Mean Variance",
    "minimum_variance": "Minimum Variance",
    "inverse_volatility": "Inverse Volatility",
    "cvar": "CVaR Aware",
    "black_litterman": "Black-Litterman",
}

# Gradient-based optimizers converge quickly on the small per-night books
# (<= top_n names), so far fewer iterations than the one-shot suite suffice.
# Each iteration costs a projected-simplex step, and this runs per night, so
# the default trades a little convergence polish for a large speedup.
_DEFAULT_ITERATIONS = 60


@dataclass(frozen=True)
class SignalPortfolioConfig:
    lookback_days: int = 63
    min_history: int = 40
    top_n: int = 25
    min_signal: float = 0.0
    method: str = "mean_variance"
    estimation_days: int = 126
    max_weight: float = 0.12
    initial_capital: float = 1_000_000.0
    fees_bps: float = 0.5
    slippage_bps: float = 1.0
    cash_rate: float = 0.0
    optimizer_iterations: int = _DEFAULT_ITERATIONS
    mean_variance_risk_aversion: float = 8.0
    kelly_fraction: float = 0.5
    cvar_alpha: float = 0.95
    black_litterman_tau: float = 0.05
    black_litterman_prior_risk_aversion: float = 2.5
    black_litterman_risk_aversion: float = 8.0


def _winsorized_mean_np(x: np.ndarray) -> np.ndarray:
    lower = np.quantile(x, 0.02, axis=0)
    upper = np.quantile(x, 0.98, axis=0)
    return np.clip(x, lower, upper).mean(axis=0)


def _covariance_np(x: np.ndarray) -> np.ndarray:
    cov = np.cov(x, rowvar=False, ddof=1)
    cov = np.atleast_2d(cov)
    jitter = max(float(np.trace(cov)) / max(cov.shape[0], 1) * 1e-8, 1e-10)
    return cov + np.eye(cov.shape[0]) * jitter


def _method_weights_np(
    method: str,
    window: np.ndarray,
    assets: list[str],
    scores: pd.Series,
    config: SignalPortfolioConfig,
) -> pd.Series:
    """Optimizer weights for one night's book from a numpy estimation window."""
    iterations = max(20, int(config.optimizer_iterations))
    if method == "score_weighted":
        values = scores.reindex(assets).clip(lower=0.0).fillna(0.0).to_numpy(dtype=float)
        if values.sum() <= 0:
            values = np.ones(len(assets), dtype=float)
        return pd.Series(project_capped_simplex(values, max_weight=config.max_weight), index=assets)
    if method == "equal_weight":
        return pd.Series(
            project_capped_simplex(np.ones(len(assets), dtype=float), max_weight=config.max_weight),
            index=assets,
        )

    cov = pd.DataFrame(_covariance_np(window), index=assets, columns=assets)
    if method == "minimum_variance":
        return minimum_variance_weights(cov, max_weight=config.max_weight, iterations=iterations)
    if method == "inverse_volatility":
        return inverse_volatility_weights(cov, max_weight=config.max_weight)
    if method == "cvar":
        return min_cvar_weights(
            pd.DataFrame(window, columns=assets),
            alpha=config.cvar_alpha,
            max_weight=config.max_weight,
            iterations=iterations,
        )

    mu = pd.Series(_winsorized_mean_np(window), index=assets)
    if method == "kelly":
        return kelly_weights(mu, cov, fraction=config.kelly_fraction, max_weight=config.max_weight)
    if method == "mean_variance":
        return mean_variance_weights(
            mu,
            cov,
            risk_aversion=config.mean_variance_risk_aversion,
            max_weight=config.max_weight,
            iterations=iterations,
        )
    if method == "black_litterman":
        from nightfall_alpha.portfolio.optimizers import black_litterman_expected_returns

        estimation = pd.DataFrame(window, columns=assets)
        market_weights = pd.Series(1.0 / len(assets), index=assets)
        bl_mu = black_litterman_expected_returns(
            estimation,
            market_weights=market_weights,
            tau=config.black_litterman_tau,
            risk_aversion=config.black_litterman_prior_risk_aversion,
        )
        return mean_variance_weights(
            bl_mu,
            cov,
            risk_aversion=config.black_litterman_risk_aversion,
            max_weight=config.max_weight,
            iterations=iterations,
        )
    raise ValueError(f"Unknown optimizer method: {method}")


def run_signal_portfolio_backtest(
    prices: pd.DataFrame,
    config: SignalPortfolioConfig | None = None,
) -> dict[str, Any]:
    cfg = config or SignalPortfolioConfig()
    if cfg.method not in OPTIMIZER_METHODS:
        raise ValueError(f"Unknown optimizer method: {cfg.method}")

    features = build_overnight_features(prices, cfg.lookback_days, cfg.min_history)
    if features.empty:
        raise ValueError("No usable price history for the signal-optimized backtest.")

    # Same candidate rule as the signal backtest: ranked top-N per night.
    candidates = features.dropna(subset=["overnight_sharpe", "next_overnight_return", "exit_date"])
    candidates = candidates[candidates["overnight_sharpe"] >= cfg.min_signal]
    if candidates.empty:
        raise ValueError("No signal candidates met the minimum signal threshold.")
    rank = candidates.groupby("date", sort=True)["overnight_sharpe"].rank(method="first", ascending=False)
    candidates = candidates[rank <= cfg.top_n].copy()
    candidates["signal_rank"] = rank[rank <= cfg.top_n].to_numpy(dtype=int)

    # Estimation matrix: overnight returns known by each night's close, kept
    # as a numpy array so the per-night window slice is a view, not a copy.
    returns_matrix = features.pivot_table(index="date", columns="symbol", values="overnight_return")
    matrix_values = returns_matrix.to_numpy(dtype=float)
    column_position = {symbol: pos for pos, symbol in enumerate(returns_matrix.columns)}
    date_position = {date: pos for pos, date in enumerate(returns_matrix.index)}

    # Per-stock cost rates are computed once over the full history: the
    # volatility scaling that drives per-stock slippage is structural, and
    # recomputing it every night would dominate the runtime.
    cost_rate_by_symbol = _per_stock_cost_rates(returns_matrix, cfg.fees_bps, cfg.slippage_bps).to_dict()

    # Pre-slice every night's book into plain numpy arrays once: the nightly
    # loop below runs tens of thousands of iterations, so it must stay clear
    # of per-day pandas construction (measured as the dominant cost).
    candidates = candidates.sort_values(["date", "signal_rank"]).reset_index(drop=True)
    split_points = np.flatnonzero(np.diff(candidates["date"].to_numpy().astype("datetime64[ns]").astype(np.int64))) + 1
    nightly = []
    for chunk in np.split(
        candidates[["date", "exit_date", "symbol", "overnight_sharpe", "next_overnight_return", "signal_rank"]].to_numpy(),
        split_points,
    ):
        nightly.append(
            (
                chunk[0, 0],  # date
                chunk[0, 1],  # exit_date
                chunk[:, 2].tolist(),  # symbols
                chunk[:, 3].astype(float),  # scores
                chunk[:, 4].astype(float),  # realized next overnight returns
                chunk[:, 5].astype(int),  # signal ranks
            )
        )

    equity = float(cfg.initial_capital)
    previous_book: dict[str, tuple[float, float]] = {}  # symbol -> (weight, realized return)
    daily_rows: list[dict[str, Any]] = []
    fallback_days = 0
    current_book = pd.DataFrame()

    for date, exit_date, symbols, scores, realized, _ranks in nightly:
        pos = date_position.get(date)
        window = np.empty((0, len(symbols)))
        if pos is not None:
            cols = [column_position[s] for s in symbols if s in column_position]
            start = max(0, pos - cfg.estimation_days + 1)
            window = matrix_values[start : pos + 1][:, cols]
            window = window[~np.isnan(window).any(axis=1)]

        fallback = len(window) < max(20, cfg.min_history) or cfg.method == "score_weighted"
        if fallback and cfg.method != "score_weighted":
            fallback_days += 1
        if fallback or cfg.method in {"score_weighted", "equal_weight"}:
            # Score weighting (also the fallback when covariances cannot be
            # estimated yet) needs no pandas round-trip through the optimizers.
            values = np.clip(scores, 0.0, None) if cfg.method == "score_weighted" or fallback else np.ones(len(symbols))
            if values.sum() <= 0:
                values = np.ones(len(symbols))
            weight_values = project_capped_simplex(values, max_weight=cfg.max_weight)
        else:
            scores_series = pd.Series(scores, index=symbols)
            weight_values = (
                _method_weights_np(cfg.method, window, symbols, scores_series, cfg)
                .reindex(symbols)
                .fillna(0.0)
                .to_numpy(dtype=float)
            )

        gross_return = float(weight_values @ realized)

        # Turnover vs last night's drifted book; entries/exits bill in full.
        turnover_total = 0.0
        cost_return = 0.0
        trade_count = 0
        if previous_book:
            prev_gross = 1.0 + sum(w * r for w, r in previous_book.values())
            if abs(prev_gross) < 1e-12:
                prev_gross = 1e-12
            drifted = {s: w * (1.0 + r) / prev_gross for s, (w, r) in previous_book.items()}
        else:
            drifted = {}
        for symbol, weight in zip(symbols, weight_values, strict=True):
            change = abs(weight - drifted.pop(symbol, 0.0))
            turnover_total += change
            cost_return += change * cost_rate_by_symbol.get(symbol, 0.0)
            trade_count += change > 1e-9
        for symbol, weight in drifted.items():  # exited positions
            change = abs(weight)
            turnover_total += change
            cost_return += change * cost_rate_by_symbol.get(symbol, 0.0)
            trade_count += change > 1e-9

        invested = float(weight_values.sum())
        cash_weight = max(0.0, 1.0 - invested)
        cash_return = cash_weight * (cfg.cash_rate / 252.0)
        net_return = gross_return + cash_return - cost_return
        starting_equity = equity
        equity = starting_equity * (1.0 + net_return)

        daily_rows.append(
            {
                "signal_date": date,
                "exit_date": exit_date,
                "starting_equity": starting_equity,
                "ending_equity": equity,
                "gross_return": gross_return,
                "cost_return": cost_return,
                "net_return": net_return,
                "turnover": turnover_total,
                "positions": int((np.abs(weight_values) > 1e-6).sum()),
                "weight_sum": invested,
                "cash_weight": cash_weight,
                # Column names performance_metrics relies on:
                "gross_exposure": invested,
                "trade_count": int(trade_count),
                "round_trip_turnover": turnover_total,
                "optimizer_fallback": bool(fallback and cfg.method != "score_weighted"),
            }
        )
        previous_book = {s: (float(w), float(r)) for s, w, r in zip(symbols, weight_values, realized, strict=True)}
        last_weights = weight_values

    if nightly:
        _, _, symbols, scores, _, ranks = nightly[-1]
        current_book = pd.DataFrame(
            {
                "symbol": symbols,
                "optimizer_weight": last_weights,
                "overnight_sharpe": scores,
                "signal_rank": ranks,
            }
        ).sort_values("optimizer_weight", ascending=False).reset_index(drop=True)

    daily = pd.DataFrame(daily_rows)
    metrics = performance_metrics(daily, cfg.initial_capital)
    metrics["cost_return_total"] = float(daily["cost_return"].sum())
    metrics["average_turnover"] = float(daily["turnover"].mean())
    metrics["optimizer_fallback_days"] = int(fallback_days)
    metrics["optimizer_fallback_share"] = float(fallback_days / len(daily)) if len(daily) else 0.0

    return {
        "daily": daily,
        "metrics": metrics,
        "current_book": current_book,
        "config": {
            "method": cfg.method,
            "method_label": OPTIMIZER_METHODS[cfg.method],
            "lookback_days": cfg.lookback_days,
            "min_history": cfg.min_history,
            "top_n": cfg.top_n,
            "min_signal": cfg.min_signal,
            "estimation_days": cfg.estimation_days,
            "max_weight": cfg.max_weight,
            "initial_capital": cfg.initial_capital,
            "fees_bps": cfg.fees_bps,
            "slippage_bps": cfg.slippage_bps,
            "cash_rate": cfg.cash_rate,
        },
    }
