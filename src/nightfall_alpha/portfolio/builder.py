from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

from nightfall_alpha.data.schema import normalize_symbol
from nightfall_alpha.portfolio.optimizers import OptimizerSuiteSettings, build_portfolio_suite, build_rebalanced_portfolio_suite
from nightfall_alpha.portfolio.risk import close_to_close_return_matrix, overnight_return_matrix, prepare_optimization_matrix


PortfolioMethod = Literal[
    "best",
    "Kelly 50%",
    "Mean Variance",
    "Minimum Variance",
    "Inverse Volatility",
    "CVaR Aware",
    "Black-Litterman",
]
ReturnModel = Literal["overnight", "close_to_close"]
RebalanceFrequency = Literal["none", "monthly", "quarterly", "annually"]


@dataclass(frozen=True)
class PortfolioBuildSpec:
    symbols: tuple[str, ...] = ()
    method: PortfolioMethod = "best"
    return_model: ReturnModel = "overnight"
    max_weight: float = 0.12
    optimizer_settings: OptimizerSuiteSettings | None = None
    risk_free_rate: float = 0.0
    initial_capital: float = 1_000_000.0
    fees_bps: float = 0.0
    slippage_bps: float = 0.0
    lookback_days: int | None = 756
    rebalance_frequency: RebalanceFrequency = "none"
    best_metric: str = "sharpe"
    allow_symbol_filtering: bool = False


def parse_symbols(symbols: str | list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    if not symbols:
        return ()
    if isinstance(symbols, str):
        raw = symbols.replace("\n", ",").replace(" ", ",").split(",")
    else:
        raw = list(symbols)
    clean = [normalize_symbol(symbol) for symbol in raw if str(symbol).strip()]
    return tuple(dict.fromkeys(clean))


def _return_matrix(prices: pd.DataFrame, model: ReturnModel) -> pd.DataFrame:
    if model == "close_to_close":
        return close_to_close_return_matrix(prices)
    return overnight_return_matrix(prices)


def _select_best(summary: pd.DataFrame, metric: str) -> str:
    if summary.empty:
        raise ValueError("No portfolio candidates were produced.")
    candidates = summary.copy()
    if metric not in candidates.columns:
        metric = "sharpe"

    candidates[metric] = pd.to_numeric(candidates[metric], errors="coerce")
    candidates = candidates.dropna(subset=[metric])
    if candidates.empty:
        return str(summary.iloc[0]["portfolio"])

    ascending = metric in {"volatility", "var_95", "cvar_95", "max_weight"}
    return str(candidates.sort_values(metric, ascending=ascending).iloc[0]["portfolio"])


def build_custom_portfolio(prices: pd.DataFrame, spec: PortfolioBuildSpec) -> dict[str, object]:
    requested_symbols = tuple(spec.symbols)
    if requested_symbols:
        available_symbols = set(prices["symbol"].dropna().astype(str).map(normalize_symbol).unique())
        missing_prices = [symbol for symbol in requested_symbols if symbol not in available_symbols]
        if missing_prices:
            raise ValueError(f"No price history found for: {', '.join(missing_prices)}")
        prices = prices[prices["symbol"].astype(str).map(normalize_symbol).isin(requested_symbols)].copy()

    matrix = _return_matrix(prices, spec.return_model)
    if matrix.empty:
        raise ValueError("No return history is available for portfolio construction.")

    if requested_symbols:
        missing = [symbol for symbol in requested_symbols if symbol not in matrix.columns]
        if missing:
            raise ValueError(f"No usable return history found for: {', '.join(missing)}")
        matrix = matrix.loc[:, list(requested_symbols)]

    matrix = matrix.dropna(axis=0, how="all")
    rebalance_frequency = str(spec.rebalance_frequency or "none").lower()
    if rebalance_frequency == "none" and spec.lookback_days and spec.lookback_days > 0:
        matrix = matrix.tail(spec.lookback_days)

    matrix, matrix_metadata = prepare_optimization_matrix(
        matrix,
        allow_symbol_filtering=spec.allow_symbol_filtering,
    )
    if matrix.shape[1] < 2:
        raise ValueError("Portfolio builder needs at least two symbols with overlapping price history.")
    if matrix.shape[0] < 20:
        raise ValueError(
            f"Portfolio builder found only {matrix.shape[0]} overlapping return rows after data alignment. "
            "Use a shorter symbol list, a shorter lookback, or refresh more history."
        )

    if rebalance_frequency == "none":
        summary, weights = build_portfolio_suite(
            matrix,
            max_weight=spec.max_weight,
            risk_free_rate=spec.risk_free_rate,
            initial_capital=spec.initial_capital,
            optimizer_settings=spec.optimizer_settings,
            fees_bps=spec.fees_bps,
            slippage_bps=spec.slippage_bps,
        )
    else:
        summary, weights = build_rebalanced_portfolio_suite(
            matrix,
            rebalance_frequency=rebalance_frequency,
            lookback_days=spec.lookback_days,
            max_weight=spec.max_weight,
            risk_free_rate=spec.risk_free_rate,
            initial_capital=spec.initial_capital,
            optimizer_settings=spec.optimizer_settings,
            fees_bps=spec.fees_bps,
            slippage_bps=spec.slippage_bps,
        )
    if summary.empty:
        if rebalance_frequency == "none":
            raise ValueError("No portfolio candidates were produced.")
        raise ValueError(
            "No rebalanced portfolio candidates were produced. Use a shorter lookback, more price history, "
            "or a lower-frequency rebalance."
        )

    selected = _select_best(summary, spec.best_metric) if spec.method == "best" else spec.method
    if selected not in set(summary["portfolio"]):
        raise ValueError(f"Unknown portfolio method: {selected}")

    selected_summary = summary[summary["portfolio"] == selected].copy()
    selected_weights = weights[weights["portfolio"] == selected].sort_values("weight", ascending=False).copy()
    return {
        "selected_portfolio": selected,
        "return_model": spec.return_model,
        "rebalance_frequency": rebalance_frequency,
        "symbols": list(matrix.columns),
        "excluded_symbols": list(matrix_metadata.get("excluded_symbols", [])),
        "input_symbol_count": matrix_metadata.get("input_symbols"),
        "coverage_start_date": matrix_metadata.get("coverage_start_date"),
        "lookback_days": len(matrix),
        "estimation_lookback_days": spec.lookback_days,
        "start_date": summary["start_date"].dropna().min() if rebalance_frequency != "none" and "start_date" in summary else matrix.index.min().strftime("%Y-%m-%d") if len(matrix.index) else None,
        "end_date": summary["end_date"].dropna().max() if rebalance_frequency != "none" and "end_date" in summary else matrix.index.max().strftime("%Y-%m-%d") if len(matrix.index) else None,
        "performance_observations": int(pd.to_numeric(summary.get("observations", pd.Series(dtype=float)), errors="coerce").max()) if not summary.empty else 0,
        "rebalance_count": int(pd.to_numeric(summary.get("rebalance_count", pd.Series(dtype=float)), errors="coerce").max()) if not summary.empty and "rebalance_count" in summary else 0,
        "summary": summary,
        "weights": weights,
        "selected_summary": selected_summary,
        "selected_weights": selected_weights,
        "optimizer_settings": spec.optimizer_settings,
    }
