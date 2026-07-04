from __future__ import annotations

import numpy as np
import pandas as pd

from nightfall_alpha.strategy.overnight import build_overnight_features


def overnight_return_matrix(prices: pd.DataFrame) -> pd.DataFrame:
    features = build_overnight_features(prices, lookback_days=2, min_history=1)
    matrix = features.pivot(index="date", columns="symbol", values="overnight_return")
    return matrix.sort_index().dropna(how="all")


def close_to_close_return_matrix(prices: pd.DataFrame) -> pd.DataFrame:
    features = build_overnight_features(prices, lookback_days=2, min_history=1)
    matrix = features.pivot(index="date", columns="symbol", values="close_to_close_return")
    return matrix.sort_index().dropna(how="all")


def historical_var_cvar(returns: pd.Series | np.ndarray, alpha: float = 0.95) -> tuple[float, float]:
    series = pd.Series(returns).dropna()
    if series.empty:
        return 0.0, 0.0
    threshold = float(series.quantile(1.0 - alpha))
    tail = series[series <= threshold]
    cvar = float(tail.mean()) if not tail.empty else threshold
    return threshold, cvar


def _minimum_required_observations(row_count: int, floor: int = 20, cap: int = 252) -> int:
    if row_count <= 0:
        return floor
    return min(cap, max(floor, int(row_count * 0.05)))


def prepare_optimization_matrix(
    return_matrix: pd.DataFrame,
    *,
    allow_symbol_filtering: bool = False,
    min_row_coverage: float = 0.75,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Create a complete return matrix without treating missing history as zero."""
    matrix = return_matrix.sort_index().dropna(axis=0, how="all").dropna(axis=1, how="all")
    metadata: dict[str, object] = {
        "input_observations": int(len(matrix)),
        "input_symbols": int(matrix.shape[1]),
        "excluded_symbols": [],
        "coverage_start_date": None,
    }
    if matrix.empty:
        metadata.update({"output_observations": 0, "output_symbols": 0})
        return matrix, metadata

    work = matrix
    if allow_symbol_filtering and work.shape[1] > 2:
        row_coverage = work.notna().mean(axis=1)
        broad_rows = row_coverage[row_coverage >= min_row_coverage]
        if not broad_rows.empty:
            coverage_start = broad_rows.index[0]
            work = work.loc[coverage_start:]
            metadata["coverage_start_date"] = coverage_start.strftime("%Y-%m-%d")

        required = _minimum_required_observations(len(work))
        recent_window = work.tail(min(10, len(work)))
        recent = recent_window.notna().any(axis=0)
        counts = work.notna().sum(axis=0)
        coverage = work.notna().mean(axis=0)

        eligible_columns: list[str] = []
        for threshold in (0.98, 0.95, 0.90, 0.80, 0.70, 0.60):
            eligible = coverage[(coverage >= threshold) & (counts >= required) & recent].index.tolist()
            if len(eligible) >= 2:
                eligible_columns = eligible
                metadata["symbol_coverage_threshold"] = threshold
                break

        if eligible_columns:
            excluded = sorted(set(work.columns) - set(eligible_columns))
            metadata["excluded_symbols"] = excluded
            work = work.loc[:, eligible_columns]

    complete = work.dropna(axis=0, how="any").dropna(axis=1, how="all")
    metadata.update(
        {
            "output_observations": int(len(complete)),
            "output_symbols": int(complete.shape[1]),
            "start_date": complete.index.min().strftime("%Y-%m-%d") if len(complete.index) else None,
            "end_date": complete.index.max().strftime("%Y-%m-%d") if len(complete.index) else None,
        }
    )
    return complete, metadata


def covariance_matrix(return_matrix: pd.DataFrame) -> pd.DataFrame:
    clean = return_matrix.dropna(how="all").dropna(axis=1, how="all").dropna(how="any")
    cov = clean.cov()
    jitter = max(float(np.trace(cov.to_numpy())) / max(len(cov), 1) * 1e-8, 1e-10)
    return cov + np.eye(len(cov)) * jitter


def expected_returns(return_matrix: pd.DataFrame, method: str = "mean") -> pd.Series:
    clean = return_matrix.dropna(how="all").dropna(axis=1, how="all").dropna(how="any")
    if clean.empty:
        return pd.Series(dtype=float)
    if method == "median":
        return clean.median()
    if method == "winsorized":
        lower = clean.quantile(0.02)
        upper = clean.quantile(0.98)
        return clean.clip(lower=lower, upper=upper, axis=1).mean()
    return clean.mean()
