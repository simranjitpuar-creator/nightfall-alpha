from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from nightfall_alpha.backtest.metrics import performance_metrics
from nightfall_alpha.portfolio.risk import covariance_matrix, expected_returns, historical_var_cvar


@dataclass(frozen=True)
class PortfolioResult:
    name: str
    weights: pd.Series
    expected_return: float
    volatility: float
    sharpe: float | None
    var_95: float
    cvar_95: float


@dataclass(frozen=True)
class OptimizerSuiteSettings:
    default_max_weight: float | None = 0.12
    kelly_fraction: float = 0.5
    kelly_max_weight: float | None = None
    mean_variance_risk_aversion: float = 8.0
    mean_variance_max_weight: float | None = None
    minimum_variance_max_weight: float | None = None
    inverse_volatility_max_weight: float | None = None
    cvar_alpha: float = 0.95
    cvar_max_weight: float | None = None
    black_litterman_tau: float = 0.05
    black_litterman_prior_risk_aversion: float = 2.5
    black_litterman_risk_aversion: float = 8.0
    black_litterman_max_weight: float | None = None

    def max_weight_for(self, key: str) -> float | None:
        value = getattr(self, f"{key}_max_weight", None)
        if value is None:
            value = self.default_max_weight
        return _sanitize_max_weight(value)

    @classmethod
    def from_mapping(
        cls,
        values: Mapping[str, object] | None,
        *,
        default_max_weight: float | None = 0.12,
    ) -> "OptimizerSuiteSettings":
        if not values:
            return cls(default_max_weight=default_max_weight)
        allowed = set(cls.__dataclass_fields__)
        clean = {key: value for key, value in values.items() if key in allowed}
        clean.setdefault("default_max_weight", default_max_weight)
        return cls(**clean)


REBALANCE_FREQUENCIES = {"none", "monthly", "quarterly", "annually"}
REBALANCE_PERIODS = {"monthly": "M", "quarterly": "Q", "annually": "Y"}


def _sanitize_max_weight(value: float | None) -> float | None:
    if value is None:
        return None
    return max(0.0, min(float(value), 1.0))


def _positive_float(value: float, fallback: float) -> float:
    number = float(value)
    return number if number > 0 else fallback


def _bounded_float(value: float, fallback: float, lower: float, upper: float) -> float:
    number = float(value)
    if not np.isfinite(number):
        return fallback
    return min(max(number, lower), upper)


def project_simplex(values: Sequence[float], target_sum: float = 1.0) -> np.ndarray:
    vector = np.asarray(values, dtype=float)
    if len(vector) == 0:
        return vector
    target = max(float(target_sum), 0.0)
    if target == 0:
        return np.zeros_like(vector)

    u = np.sort(vector)[::-1]
    cssv = np.cumsum(u) - target
    indices = np.arange(1, len(vector) + 1)
    condition = u - cssv / indices > 0
    if not condition.any():
        return np.ones_like(vector) * target / len(vector)
    rho = indices[condition][-1]
    theta = cssv[condition][-1] / rho
    return np.maximum(vector - theta, 0.0)


def project_capped_simplex(values: Sequence[float], max_weight: float | None = None, target_sum: float = 1.0) -> np.ndarray:
    vector = np.asarray(values, dtype=float)
    if len(vector) == 0:
        return vector
    if max_weight is None:
        return project_simplex(vector, target_sum)

    cap = max(float(max_weight), 0.0)
    target = min(max(float(target_sum), 0.0), cap * len(vector))
    if cap == 0 or target == 0:
        return np.zeros_like(vector)

    result = np.zeros_like(vector)
    free = np.ones(len(vector), dtype=bool)
    remaining_target = target

    for _ in range(len(vector) + 1):
        projected = project_simplex(vector[free], remaining_target)
        over = projected > cap + 1e-12
        if not over.any():
            result[free] = projected
            break
        free_indices = np.where(free)[0]
        capped_indices = free_indices[over]
        result[capped_indices] = cap
        free[capped_indices] = False
        remaining_target = target - result.sum()
        if remaining_target <= 1e-12 or not free.any():
            break

    return np.clip(result, 0.0, cap)


def _align_inputs(mu: pd.Series, cov: pd.DataFrame) -> tuple[list[str], np.ndarray, np.ndarray]:
    assets = [asset for asset in mu.index if asset in cov.index and asset in cov.columns]
    if not assets:
        return [], np.array([]), np.empty((0, 0))
    mu_vec = mu.loc[assets].fillna(0.0).to_numpy(dtype=float)
    cov_mat = cov.loc[assets, assets].fillna(0.0).to_numpy(dtype=float)
    cov_mat = (cov_mat + cov_mat.T) / 2.0
    cov_mat = cov_mat + np.eye(len(assets)) * 1e-10
    return assets, mu_vec, cov_mat


def _series_weights(assets: Sequence[str], weights: np.ndarray) -> pd.Series:
    return pd.Series(weights, index=list(assets), dtype=float).sort_values(ascending=False)


def mean_variance_weights(
    mu: pd.Series,
    cov: pd.DataFrame,
    risk_aversion: float = 8.0,
    max_weight: float | None = None,
    iterations: int = 750,
) -> pd.Series:
    assets, mu_vec, cov_mat = _align_inputs(mu, cov)
    if not assets:
        return pd.Series(dtype=float)

    n_assets = len(assets)
    weights = np.ones(n_assets) / n_assets
    largest_eigenvalue = max(float(np.linalg.eigvalsh(cov_mat).max()), 1e-8)
    step = 1.0 / (risk_aversion * largest_eigenvalue + 1e-8)

    for _ in range(iterations):
        gradient = risk_aversion * cov_mat @ weights - mu_vec
        weights = project_capped_simplex(weights - step * gradient, max_weight=max_weight)

    return _series_weights(assets, weights)


def minimum_variance_weights(cov: pd.DataFrame, max_weight: float | None = None, iterations: int = 750) -> pd.Series:
    assets = list(cov.index)
    if not assets:
        return pd.Series(dtype=float)
    cov_mat = cov.loc[assets, assets].fillna(0.0).to_numpy(dtype=float)
    cov_mat = (cov_mat + cov_mat.T) / 2.0 + np.eye(len(assets)) * 1e-10
    weights = np.ones(len(assets)) / len(assets)
    largest_eigenvalue = max(float(np.linalg.eigvalsh(cov_mat).max()), 1e-8)
    step = 1.0 / (2.0 * largest_eigenvalue + 1e-8)

    for _ in range(iterations):
        gradient = 2.0 * cov_mat @ weights
        weights = project_capped_simplex(weights - step * gradient, max_weight=max_weight)

    return _series_weights(assets, weights)


def inverse_volatility_weights(cov: pd.DataFrame, max_weight: float | None = None) -> pd.Series:
    assets = list(cov.index)
    if not assets:
        return pd.Series(dtype=float)
    variance = np.diag(cov.loc[assets, assets].to_numpy(dtype=float))
    inverse_vol = 1.0 / np.sqrt(np.maximum(variance, 1e-12))
    weights = project_capped_simplex(inverse_vol, max_weight=max_weight)
    return _series_weights(assets, weights)


def kelly_weights(
    mu: pd.Series,
    cov: pd.DataFrame,
    fraction: float = 0.5,
    max_weight: float | None = None,
) -> pd.Series:
    assets, mu_vec, cov_mat = _align_inputs(mu, cov)
    if not assets:
        return pd.Series(dtype=float)

    raw = np.linalg.pinv(cov_mat) @ mu_vec
    raw = np.clip(raw, 0.0, None)
    if raw.sum() <= 0:
        return minimum_variance_weights(pd.DataFrame(cov_mat, index=assets, columns=assets), max_weight=max_weight)

    target = min(max(float(fraction), 0.0), 1.0)
    weights = project_capped_simplex(raw, max_weight=max_weight, target_sum=target)
    return _series_weights(assets, weights)


def min_cvar_weights(
    return_matrix: pd.DataFrame,
    alpha: float = 0.95,
    max_weight: float | None = None,
    iterations: int = 500,
) -> pd.Series:
    clean = return_matrix.dropna(how="all").dropna(axis=1, how="all").dropna(how="any")
    assets = list(clean.columns)
    if not assets:
        return pd.Series(dtype=float)

    cov = covariance_matrix(clean)
    weights = inverse_volatility_weights(cov, max_weight=max_weight).reindex(assets).fillna(0.0).to_numpy()
    x = clean.to_numpy(dtype=float)

    for iteration in range(iterations):
        portfolio_returns = x @ weights
        threshold = np.quantile(portfolio_returns, 1.0 - alpha)
        tail = x[portfolio_returns <= threshold]
        if len(tail) == 0:
            break
        gradient = -tail.mean(axis=0)
        step = 0.15 / np.sqrt(iteration + 1.0)
        weights = project_capped_simplex(weights - step * gradient, max_weight=max_weight)

    return _series_weights(assets, weights)


def black_litterman_expected_returns(
    return_matrix: pd.DataFrame,
    market_weights: pd.Series | None = None,
    views: Sequence[Mapping[str, object]] | None = None,
    tau: float = 0.05,
    risk_aversion: float = 2.5,
) -> pd.Series:
    clean = return_matrix.dropna(how="all").dropna(axis=1, how="all").dropna(how="any")
    assets = list(clean.columns)
    if not assets:
        return pd.Series(dtype=float)

    cov = covariance_matrix(clean).loc[assets, assets].to_numpy(dtype=float)
    if market_weights is None:
        market = np.ones(len(assets)) / len(assets)
    else:
        market = market_weights.reindex(assets).fillna(0.0).to_numpy(dtype=float)
        market = project_simplex(market, 1.0)

    prior = risk_aversion * cov @ market
    if not views:
        return pd.Series(prior, index=assets)

    p_rows: list[np.ndarray] = []
    q_values: list[float] = []
    asset_index = {asset: i for i, asset in enumerate(assets)}

    for view in views:
        weights_map = view.get("weights")
        absolute_asset = view.get("asset")
        view_return = float(view.get("return", 0.0))
        row = np.zeros(len(assets))

        if isinstance(weights_map, Mapping):
            for asset, weight in weights_map.items():
                if asset in asset_index:
                    row[asset_index[asset]] = float(weight)
        elif isinstance(absolute_asset, str) and absolute_asset in asset_index:
            row[asset_index[absolute_asset]] = 1.0

        if np.abs(row).sum() > 0:
            p_rows.append(row)
            q_values.append(view_return)

    if not p_rows:
        return pd.Series(prior, index=assets)

    p_matrix = np.vstack(p_rows)
    q_vector = np.asarray(q_values, dtype=float)
    tau_cov = tau * cov
    omega_diag = np.diag(p_matrix @ tau_cov @ p_matrix.T)
    omega = np.diag(np.maximum(omega_diag, 1e-8))

    posterior_cov_inv = np.linalg.pinv(tau_cov) + p_matrix.T @ np.linalg.pinv(omega) @ p_matrix
    posterior_rhs = np.linalg.pinv(tau_cov) @ prior + p_matrix.T @ np.linalg.pinv(omega) @ q_vector
    posterior = np.linalg.pinv(posterior_cov_inv) @ posterior_rhs
    return pd.Series(posterior, index=assets)


def _suite_settings(
    optimizer_settings: OptimizerSuiteSettings | Mapping[str, object] | None,
    max_weight: float | None,
) -> OptimizerSuiteSettings:
    if isinstance(optimizer_settings, OptimizerSuiteSettings):
        return optimizer_settings
    return OptimizerSuiteSettings.from_mapping(
        optimizer_settings,
        default_max_weight=max_weight,
    )


def _optimizer_weight_methods(
    clean: pd.DataFrame,
    suite_settings: OptimizerSuiteSettings,
    *,
    iterations: int | None = None,
    cvar_iterations: int | None = None,
) -> tuple[dict[str, pd.Series], dict[str, float | None], dict[str, str]]:
    mu = expected_returns(clean, method="winsorized")
    cov = covariance_matrix(clean)
    market_weights = pd.Series(1.0 / len(clean.columns), index=clean.columns)
    bl_tau = _positive_float(suite_settings.black_litterman_tau, 0.05)
    bl_prior_risk = _positive_float(suite_settings.black_litterman_prior_risk_aversion, 2.5)
    bl_mu = black_litterman_expected_returns(
        clean,
        market_weights=market_weights,
        tau=bl_tau,
        risk_aversion=bl_prior_risk,
    )

    kelly_fraction = _bounded_float(suite_settings.kelly_fraction, 0.5, 0.0, 1.0)
    mean_variance_risk = _positive_float(suite_settings.mean_variance_risk_aversion, 8.0)
    cvar_alpha = _bounded_float(suite_settings.cvar_alpha, 0.95, 0.5, 0.999)
    bl_optimizer_risk = _positive_float(suite_settings.black_litterman_risk_aversion, 8.0)
    gradient_iterations = int(iterations or 750)
    tail_iterations = int(cvar_iterations or 500)
    caps = {
        "Kelly 50%": suite_settings.max_weight_for("kelly"),
        "Mean Variance": suite_settings.max_weight_for("mean_variance"),
        "Minimum Variance": suite_settings.max_weight_for("minimum_variance"),
        "Inverse Volatility": suite_settings.max_weight_for("inverse_volatility"),
        "CVaR Aware": suite_settings.max_weight_for("cvar"),
        "Black-Litterman": suite_settings.max_weight_for("black_litterman"),
    }
    methods = {
        "Kelly 50%": kelly_weights(mu, cov, fraction=kelly_fraction, max_weight=caps["Kelly 50%"]),
        "Mean Variance": mean_variance_weights(
            mu,
            cov,
            risk_aversion=mean_variance_risk,
            max_weight=caps["Mean Variance"],
            iterations=gradient_iterations,
        ),
        "Minimum Variance": minimum_variance_weights(
            cov,
            max_weight=caps["Minimum Variance"],
            iterations=gradient_iterations,
        ),
        "Inverse Volatility": inverse_volatility_weights(cov, max_weight=caps["Inverse Volatility"]),
        "CVaR Aware": min_cvar_weights(
            clean,
            alpha=cvar_alpha,
            max_weight=caps["CVaR Aware"],
            iterations=tail_iterations,
        ),
        "Black-Litterman": mean_variance_weights(
            bl_mu,
            cov,
            risk_aversion=bl_optimizer_risk,
            max_weight=caps["Black-Litterman"],
            iterations=gradient_iterations,
        ),
    }
    method_parameters = {
        "Kelly 50%": f"fraction={kelly_fraction:.3g}",
        "Mean Variance": f"risk_aversion={mean_variance_risk:.3g}",
        "Minimum Variance": "minimum risk",
        "Inverse Volatility": "inverse volatility",
        "CVaR Aware": f"alpha={cvar_alpha:.3g}",
        "Black-Litterman": f"tau={bl_tau:.3g}; prior_risk={bl_prior_risk:.3g}; opt_risk={bl_optimizer_risk:.3g}",
    }
    return methods, caps, method_parameters


def portfolio_statistics(
    name: str,
    weights: pd.Series,
    return_matrix: pd.DataFrame,
    risk_free_rate: float = 0.0,
) -> PortfolioResult:
    clean = return_matrix.dropna(how="all").dropna(axis=1, how="all").dropna(how="any")
    weights = weights.reindex(clean.columns).fillna(0.0)
    portfolio_returns = clean @ weights
    annual_return = float(portfolio_returns.mean() * 252.0)
    annual_vol = float(portfolio_returns.std(ddof=0) * np.sqrt(252.0))
    sharpe = (annual_return - risk_free_rate) / annual_vol if annual_vol > 0 else None
    var_95, cvar_95 = historical_var_cvar(portfolio_returns, alpha=0.95)
    return PortfolioResult(
        name=name,
        weights=weights.sort_values(ascending=False),
        expected_return=annual_return,
        volatility=annual_vol,
        sharpe=sharpe,
        var_95=var_95,
        cvar_95=cvar_95,
    )


def portfolio_metric_details(
    weights: pd.Series,
    return_matrix: pd.DataFrame,
    risk_free_rate: float = 0.0,
    initial_capital: float = 1_000_000.0,
    fees_bps: float = 0.0,
    slippage_bps: float = 0.0,
) -> dict[str, float | int | str | None]:
    clean = return_matrix.dropna(how="all").dropna(axis=1, how="all").dropna(how="any").sort_index()
    weights = weights.reindex(clean.columns).fillna(0.0)
    portfolio_returns = clean @ weights
    if portfolio_returns.empty:
        return {}

    equity = float(initial_capital)
    gross_exposure = float(weights.abs().sum())
    positions = int((weights.abs() > 1e-6).sum())
    cost_per_side = max(float(fees_bps) + float(slippage_bps), 0.0) / 10_000.0
    rows: list[dict[str, float | int | object]] = []
    for index, (date, gross_return) in enumerate(portfolio_returns.items()):
        turnover_value = gross_exposure if index == 0 else 0.0
        cost_return = turnover_value * cost_per_side
        net_return = float(gross_return) - cost_return
        starting_equity = equity
        equity = starting_equity * (1.0 + net_return)
        rows.append(
            {
                "signal_date": date,
                "exit_date": date,
                "starting_equity": starting_equity,
                "ending_equity": equity,
                "net_return": net_return,
                "gross_return": float(gross_return),
                "cost_return": cost_return,
                "gross_exposure": gross_exposure,
                "trade_count": positions,
                "round_trip_turnover": turnover_value,
            }
        )
    metrics = performance_metrics(
        pd.DataFrame(rows),
        initial_capital=float(initial_capital),
        risk_free_rate=risk_free_rate,
    )

    metrics["expected_return"] = metrics.get("annualized_return")
    metrics["volatility"] = metrics.get("annualized_volatility")
    metrics["positions"] = positions
    if int(metrics.get("observations") or 0) < 252:
        metrics["cagr"] = None
        metrics["calmar"] = None
    return metrics


def _metric_details_from_returns(
    portfolio_returns: pd.Series,
    *,
    risk_free_rate: float = 0.0,
    initial_capital: float = 1_000_000.0,
    gross_exposure: pd.Series | float = 1.0,
    trade_count: pd.Series | int = 0,
    turnover: pd.Series | float = 0.0,
    fees_bps: float = 0.0,
    slippage_bps: float = 0.0,
) -> dict[str, float | int | str | None]:
    portfolio_returns = portfolio_returns.dropna().sort_index()
    if portfolio_returns.empty:
        return {}

    equity = float(initial_capital)
    cost_per_side = max(float(fees_bps) + float(slippage_bps), 0.0) / 10_000.0
    rows: list[dict[str, float | int | object]] = []
    for date, gross_return in portfolio_returns.items():
        starting_equity = equity
        exposure_value = (
            float(gross_exposure.loc[date])
            if isinstance(gross_exposure, pd.Series) and date in gross_exposure.index
            else float(gross_exposure)
        )
        trade_count_value = (
            int(trade_count.loc[date])
            if isinstance(trade_count, pd.Series) and date in trade_count.index
            else int(trade_count)
        )
        turnover_value = (
            float(turnover.loc[date])
            if isinstance(turnover, pd.Series) and date in turnover.index
            else float(turnover)
        )
        cost_return = turnover_value * cost_per_side
        net_return = float(gross_return) - cost_return
        equity = starting_equity * (1.0 + net_return)
        rows.append(
            {
                "signal_date": date,
                "exit_date": date,
                "starting_equity": starting_equity,
                "ending_equity": equity,
                "net_return": net_return,
                "gross_return": float(gross_return),
                "cost_return": cost_return,
                "gross_exposure": exposure_value,
                "trade_count": trade_count_value,
                "round_trip_turnover": turnover_value,
            }
        )

    metrics = performance_metrics(
        pd.DataFrame(rows),
        initial_capital=float(initial_capital),
        risk_free_rate=risk_free_rate,
    )
    metrics["expected_return"] = metrics.get("annualized_return")
    metrics["volatility"] = metrics.get("annualized_volatility")
    if int(metrics.get("observations") or 0) < 252:
        metrics["cagr"] = None
        metrics["calmar"] = None
    return metrics


def _summary_row(
    *,
    name: str,
    details: dict[str, float | int | str | None],
    var_95: float | None,
    cvar_95: float | None,
    weights: pd.Series,
    cap: float | None,
    parameters: str,
    rebalance_frequency: str = "none",
    rebalance_count: int = 0,
    average_turnover: float | None = 0.0,
    last_rebalance_date: str | None = None,
) -> dict[str, float | int | str | None]:
    invested_weight = float(weights.sum()) if not weights.empty else 0.0
    gross_exposure = float(weights.abs().sum()) if not weights.empty else 0.0
    return {
        "portfolio": name,
        "initial_capital": details.get("initial_capital"),
        "final_equity": details.get("final_equity"),
        "total_return": details.get("total_return"),
        "cagr": details.get("cagr"),
        "start_date": details.get("start_date"),
        "end_date": details.get("end_date"),
        "elapsed_years": details.get("elapsed_years"),
        "annualized_return": details.get("annualized_return"),
        "annualized_volatility": details.get("annualized_volatility"),
        "expected_return": details.get("annualized_return"),
        "volatility": details.get("annualized_volatility"),
        "sharpe": details.get("sharpe"),
        "sortino": details.get("sortino"),
        "calmar": details.get("calmar"),
        "rolling_sharpe_1y": details.get("rolling_sharpe_1y"),
        "rolling_sharpe_3y": details.get("rolling_sharpe_3y"),
        "rolling_sharpe_5y": details.get("rolling_sharpe_5y"),
        "rolling_sortino_1y": details.get("rolling_sortino_1y"),
        "rolling_sortino_3y": details.get("rolling_sortino_3y"),
        "rolling_sortino_5y": details.get("rolling_sortino_5y"),
        "rolling_calmar_1y": details.get("rolling_calmar_1y"),
        "rolling_calmar_3y": details.get("rolling_calmar_3y"),
        "rolling_calmar_5y": details.get("rolling_calmar_5y"),
        "max_drawdown": details.get("max_drawdown"),
        "var_95": var_95,
        "cvar_95": cvar_95,
        "win_rate": details.get("win_rate"),
        "best_day": details.get("best_day"),
        "worst_day": details.get("worst_day"),
        "profit_factor": details.get("profit_factor"),
        "gross_return_before_costs": details.get("gross_return_before_costs"),
        "total_cost_return": details.get("total_cost_return"),
        "average_round_trip_turnover": details.get("average_round_trip_turnover"),
        "weight_sum": invested_weight,
        "gross_exposure": gross_exposure,
        "cash_weight": max(0.0, 1.0 - invested_weight),
        "max_weight_limit": cap,
        "max_weight": float(weights.max()) if not weights.empty else 0.0,
        "optimizer_parameters": parameters,
        "positions": int((weights.abs() > 1e-6).sum()),
        "observations": details.get("observations"),
        "rebalance_frequency": rebalance_frequency,
        "rebalance_count": rebalance_count,
        "average_turnover": average_turnover,
        "last_rebalance_date": last_rebalance_date,
    }


def build_portfolio_suite(
    return_matrix: pd.DataFrame,
    max_weight: float | None = 0.12,
    risk_free_rate: float = 0.0,
    initial_capital: float = 1_000_000.0,
    optimizer_settings: OptimizerSuiteSettings | Mapping[str, object] | None = None,
    fees_bps: float = 0.0,
    slippage_bps: float = 0.0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    clean = return_matrix.dropna(how="all").dropna(axis=1, how="all").dropna(how="any").sort_index()
    if clean.empty:
        return pd.DataFrame(), pd.DataFrame()

    suite_settings = _suite_settings(optimizer_settings, max_weight)
    methods, caps, method_parameters = _optimizer_weight_methods(clean, suite_settings)

    summary_rows: list[dict[str, float | int | str | None]] = []
    weight_rows: list[dict[str, float | str]] = []
    for name, weights in methods.items():
        stats = portfolio_statistics(name, weights, clean, risk_free_rate=risk_free_rate)
        details = portfolio_metric_details(
            weights,
            clean,
            risk_free_rate=risk_free_rate,
            initial_capital=initial_capital,
            fees_bps=fees_bps,
            slippage_bps=slippage_bps,
        )
        summary_rows.append(
            _summary_row(
                name=name,
                details=details,
                var_95=details.get("var_95"),
                cvar_95=details.get("cvar_95"),
                weights=stats.weights,
                cap=caps[name],
                parameters=method_parameters[name],
            )
        )
        for symbol, weight in stats.weights.items():
            if abs(weight) > 1e-6:
                weight_rows.append({"portfolio": name, "symbol": symbol, "weight": float(weight)})

    return pd.DataFrame(summary_rows), pd.DataFrame(weight_rows)


def _minimum_rebalance_history(row_count: int, lookback_days: int | None) -> int:
    if lookback_days and lookback_days > 0:
        return max(20, int(lookback_days))
    return min(252, max(20, int(row_count * 0.25)))


def _rebalance_dates(clean: pd.DataFrame, frequency: str, min_history: int) -> list[pd.Timestamp]:
    if frequency not in REBALANCE_PERIODS:
        return []
    index = pd.DatetimeIndex(clean.index)
    eligible = index[min_history:]
    if len(eligible) == 0:
        return []
    periods = eligible.to_period(REBALANCE_PERIODS[frequency])
    return [pd.Timestamp(value) for value in pd.Series(eligible, index=eligible).groupby(periods).first().tolist()]


def build_rebalanced_portfolio_suite(
    return_matrix: pd.DataFrame,
    *,
    rebalance_frequency: str,
    lookback_days: int | None = 756,
    max_weight: float | None = 0.12,
    risk_free_rate: float = 0.0,
    initial_capital: float = 1_000_000.0,
    optimizer_settings: OptimizerSuiteSettings | Mapping[str, object] | None = None,
    fees_bps: float = 0.0,
    slippage_bps: float = 0.0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    frequency = str(rebalance_frequency or "none").lower()
    if frequency == "none":
        return build_portfolio_suite(
            return_matrix,
            max_weight=max_weight,
            risk_free_rate=risk_free_rate,
            initial_capital=initial_capital,
            optimizer_settings=optimizer_settings,
            fees_bps=fees_bps,
            slippage_bps=slippage_bps,
        )
    if frequency not in REBALANCE_PERIODS:
        raise ValueError("Rebalance frequency must be monthly, quarterly, annually, or none.")

    clean = return_matrix.dropna(how="all").dropna(axis=1, how="all").dropna(how="any").sort_index()
    if clean.empty:
        return pd.DataFrame(), pd.DataFrame()

    min_history = _minimum_rebalance_history(len(clean), lookback_days)
    dates = _rebalance_dates(clean, frequency, min_history)
    if not dates:
        return pd.DataFrame(), pd.DataFrame()

    suite_settings = _suite_settings(optimizer_settings, max_weight)
    returns_by_portfolio: dict[str, list[pd.Series]] = {}
    exposure_by_portfolio: dict[str, list[pd.Series]] = {}
    count_by_portfolio: dict[str, list[pd.Series]] = {}
    turnover_by_portfolio: dict[str, list[pd.Series]] = {}
    rebalance_counts: dict[str, int] = {}
    latest_weights: dict[str, pd.Series] = {}
    latest_caps: dict[str, float | None] = {}
    latest_parameters: dict[str, str] = {}
    previous_weights: dict[str, pd.Series] = {}
    method_order: list[str] = []
    weight_rows: list[dict[str, float | str]] = []

    date_positions = {pd.Timestamp(date): position for position, date in enumerate(clean.index)}
    for date_index, rebalance_date in enumerate(dates):
        start_pos = date_positions.get(pd.Timestamp(rebalance_date))
        if start_pos is None or start_pos <= 0:
            continue
        history = clean.iloc[:start_pos]
        if lookback_days and lookback_days > 0:
            history = history.tail(int(lookback_days))
        if len(history) < 20:
            continue

        methods, caps, method_parameters = _optimizer_weight_methods(
            history,
            suite_settings,
            iterations=220,
            cvar_iterations=160,
        )
        if not method_order:
            method_order = list(methods.keys())

        end_pos = date_positions.get(pd.Timestamp(dates[date_index + 1]), len(clean)) if date_index + 1 < len(dates) else len(clean)
        period = clean.iloc[start_pos:end_pos]
        if period.empty:
            continue

        for name in method_order:
            weights = methods.get(name, pd.Series(dtype=float)).reindex(clean.columns).fillna(0.0)
            prior = previous_weights.get(name, pd.Series(0.0, index=clean.columns)).reindex(clean.columns).fillna(0.0)
            turnover_value = float((weights - prior).abs().sum())
            portfolio_returns = period @ weights
            exposure = float(weights.abs().sum())
            positions = int((weights.abs() > 1e-6).sum())
            turnover = pd.Series(0.0, index=period.index, dtype=float)
            if not turnover.empty:
                turnover.iloc[0] = turnover_value

            returns_by_portfolio.setdefault(name, []).append(portfolio_returns)
            exposure_by_portfolio.setdefault(name, []).append(pd.Series(exposure, index=period.index, dtype=float))
            count_by_portfolio.setdefault(name, []).append(pd.Series(positions, index=period.index, dtype=float))
            turnover_by_portfolio.setdefault(name, []).append(turnover)
            rebalance_counts[name] = rebalance_counts.get(name, 0) + 1
            previous_weights[name] = weights
            latest_weights[name] = weights.sort_values(ascending=False)
            latest_caps[name] = caps.get(name)
            latest_parameters[name] = method_parameters.get(name, "")

            for symbol, weight in weights.sort_values(ascending=False).items():
                if abs(weight) > 1e-6:
                    weight_rows.append(
                        {
                            "portfolio": name,
                            "rebalance_date": rebalance_date.strftime("%Y-%m-%d"),
                            "symbol": symbol,
                            "weight": float(weight),
                        }
                    )

    summary_rows: list[dict[str, float | int | str | None]] = []
    for name in method_order:
        if not returns_by_portfolio.get(name):
            continue
        portfolio_returns = pd.concat(returns_by_portfolio[name]).sort_index()
        exposure = pd.concat(exposure_by_portfolio[name]).sort_index()
        trade_count = pd.concat(count_by_portfolio[name]).sort_index()
        turnover = pd.concat(turnover_by_portfolio[name]).sort_index()
        details = _metric_details_from_returns(
            portfolio_returns,
            risk_free_rate=risk_free_rate,
            initial_capital=initial_capital,
            gross_exposure=exposure,
            trade_count=trade_count,
            turnover=turnover,
            fees_bps=fees_bps,
            slippage_bps=slippage_bps,
        )
        active_turnover = turnover[turnover > 0]
        latest = latest_weights.get(name, pd.Series(dtype=float))
        latest_date = None
        if not weight_rows:
            latest_date = None
        else:
            portfolio_dates = [row["rebalance_date"] for row in weight_rows if row["portfolio"] == name]
            latest_date = str(max(portfolio_dates)) if portfolio_dates else None
        summary_rows.append(
            _summary_row(
                name=name,
                details=details,
                var_95=details.get("var_95"),
                cvar_95=details.get("cvar_95"),
                weights=latest,
                cap=latest_caps.get(name),
                parameters=latest_parameters.get(name, ""),
                rebalance_frequency=frequency,
                rebalance_count=rebalance_counts.get(name, 0),
                average_turnover=float(active_turnover.mean()) if not active_turnover.empty else 0.0,
                last_rebalance_date=latest_date,
            )
        )

    return pd.DataFrame(summary_rows), pd.DataFrame(weight_rows)
