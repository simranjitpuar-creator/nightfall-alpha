from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def compute_drawdown(equity: pd.Series) -> pd.Series:
    if equity.empty:
        return pd.Series(dtype=float)
    peak = equity.cummax()
    return equity / peak - 1.0


def _annualized_excess_return(returns: pd.Series, risk_free_rate: float, periods_per_year: int) -> float:
    return float(returns.mean() * periods_per_year - risk_free_rate)


def _downside_deviation(returns: pd.Series, risk_free_rate: float, periods_per_year: int) -> float:
    minimum_acceptable_return = float(risk_free_rate) / float(periods_per_year)
    downside = (returns - minimum_acceptable_return).clip(upper=0.0)
    return float(math.sqrt(float((downside**2).mean())) * math.sqrt(periods_per_year))


def _rolling_ratio_metrics(
    daily: pd.DataFrame,
    risk_free_rate: float,
    periods_per_year: int,
) -> dict[str, float | None]:
    metrics: dict[str, float | None] = {}
    clean = pd.DataFrame(
        {
            "net_return": pd.to_numeric(daily.get("net_return", pd.Series(dtype=float)), errors="coerce"),
            "ending_equity": pd.to_numeric(daily.get("ending_equity", pd.Series(dtype=float)), errors="coerce"),
        }
    )
    if "exit_date" in daily:
        clean["exit_date"] = pd.to_datetime(daily["exit_date"], errors="coerce")
    if "starting_equity" in daily:
        clean["starting_equity"] = pd.to_numeric(daily["starting_equity"], errors="coerce")
    clean = clean.dropna(subset=["net_return", "ending_equity"]).reset_index(drop=True)
    if "exit_date" in clean:
        clean = clean.sort_values("exit_date", kind="mergesort").reset_index(drop=True)

    for label, years in (("1y", 1), ("3y", 3), ("5y", 5)):
        window_size = int(periods_per_year * years)
        sharpe_key = f"rolling_sharpe_{label}"
        sortino_key = f"rolling_sortino_{label}"
        calmar_key = f"rolling_calmar_{label}"
        metrics.update({sharpe_key: None, sortino_key: None, calmar_key: None})
        if window_size < 2 or len(clean) < window_size:
            continue

        window = clean.tail(window_size)
        returns = window["net_return"]
        annualized_excess_return = _annualized_excess_return(returns, risk_free_rate, periods_per_year)
        annualized_volatility = float(returns.std(ddof=0) * math.sqrt(periods_per_year))
        if annualized_volatility > 0:
            metrics[sharpe_key] = annualized_excess_return / annualized_volatility

        downside_volatility = _downside_deviation(returns, risk_free_rate, periods_per_year)
        if downside_volatility > 0:
            metrics[sortino_key] = annualized_excess_return / downside_volatility

        start_equity = None
        if "starting_equity" in window and pd.notna(window["starting_equity"].iloc[0]):
            start_equity = float(window["starting_equity"].iloc[0])
        if not start_equity or start_equity <= 0:
            first_return = float(window["net_return"].iloc[0])
            first_ending_equity = float(window["ending_equity"].iloc[0])
            if 1.0 + first_return > 0:
                start_equity = first_ending_equity / (1.0 + first_return)

        ending_equity = float(window["ending_equity"].iloc[-1])
        if start_equity and start_equity > 0 and ending_equity > 0:
            cagr = (ending_equity / start_equity) ** (periods_per_year / len(window)) - 1.0
            equity_path = pd.concat(
                [pd.Series([start_equity], dtype=float), window["ending_equity"].reset_index(drop=True)],
                ignore_index=True,
            )
            max_drawdown = float(compute_drawdown(equity_path).min())
            if max_drawdown < 0:
                metrics[calmar_key] = cagr / abs(max_drawdown)

    return metrics


def _date_bounds(daily: pd.DataFrame) -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
    start: pd.Timestamp | None = None
    end: pd.Timestamp | None = None

    for column in ("signal_date", "date", "exit_date"):
        if column in daily:
            dates = pd.to_datetime(daily[column], errors="coerce").dropna()
            if not dates.empty:
                start = pd.Timestamp(dates.min())
                break

    for column in ("exit_date", "date", "signal_date"):
        if column in daily:
            dates = pd.to_datetime(daily[column], errors="coerce").dropna()
            if not dates.empty:
                end = pd.Timestamp(dates.max())
                break

    return start, end


def _elapsed_years(
    daily: pd.DataFrame,
    observations: int,
    periods_per_year: int,
) -> tuple[float, str | None, str | None]:
    start, end = _date_bounds(daily)
    if start is not None and end is not None and end > start:
        years = max(float((end - start).days) / 365.25, 1.0 / float(periods_per_year))
        return years, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")

    fallback_years = float(observations) / float(periods_per_year) if observations else 0.0
    return fallback_years, None, None


def performance_metrics(
    daily: pd.DataFrame,
    initial_capital: float,
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252,
) -> dict[str, float | int | str | None]:
    if daily.empty:
        metrics: dict[str, float | int | str | None] = {
            "initial_capital": initial_capital,
            "final_equity": initial_capital,
            "observations": 0,
            "elapsed_years": 0.0,
            "start_date": None,
            "end_date": None,
        }
        metrics.update(_rolling_ratio_metrics(daily, risk_free_rate=risk_free_rate, periods_per_year=periods_per_year))
        return metrics

    returns = pd.to_numeric(daily["net_return"], errors="coerce").dropna()
    equity = pd.to_numeric(daily["ending_equity"], errors="coerce").dropna()
    observations = int(len(returns))
    years, start_date, end_date = _elapsed_years(daily, observations, periods_per_year)

    final_equity = float(equity.iloc[-1])
    total_return = final_equity / float(initial_capital) - 1.0
    cagr = (final_equity / float(initial_capital)) ** (1.0 / years) - 1.0 if years > 0 else 0.0
    annualized_return = float(returns.mean() * periods_per_year)
    annualized_excess_return = _annualized_excess_return(returns, risk_free_rate, periods_per_year)
    annualized_volatility = float(returns.std(ddof=0) * math.sqrt(periods_per_year))
    sharpe = (
        annualized_excess_return / annualized_volatility
        if annualized_volatility > 0
        else None
    )

    downside_volatility = _downside_deviation(returns, risk_free_rate, periods_per_year)
    sortino = annualized_excess_return / downside_volatility if downside_volatility > 0 else None

    equity_path = pd.concat([pd.Series([float(initial_capital)], dtype=float), equity.reset_index(drop=True)], ignore_index=True)
    drawdown = compute_drawdown(equity_path)
    max_drawdown = float(drawdown.min()) if not drawdown.empty else 0.0
    calmar = cagr / abs(max_drawdown) if max_drawdown < 0 else None

    winning = returns[returns > 0]
    losing = returns[returns < 0]
    var_95 = float(returns.quantile(0.05))
    cvar_95 = float(returns[returns <= var_95].mean()) if (returns <= var_95).any() else var_95

    gross_pnl = pd.to_numeric(daily.get("gross_return", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    cost_return = pd.to_numeric(daily.get("cost_return", pd.Series(dtype=float)), errors="coerce").fillna(0.0)

    metrics = {
        "initial_capital": float(initial_capital),
        "final_equity": final_equity,
        "total_return": total_return,
        "cagr": cagr,
        "annualized_return": annualized_return,
        "annualized_volatility": annualized_volatility,
        "sharpe": sharpe,
        "sortino": sortino,
        "max_drawdown": max_drawdown,
        "calmar": calmar,
        "win_rate": float((returns > 0).mean()),
        "average_daily_return": float(returns.mean()),
        "best_day": float(returns.max()),
        "worst_day": float(returns.min()),
        "var_95": var_95,
        "cvar_95": cvar_95,
        "skew": float(returns.skew()) if observations > 2 else None,
        "kurtosis": float(returns.kurtosis()) if observations > 3 else None,
        "profit_factor": float(winning.sum() / abs(losing.sum())) if abs(losing.sum()) > 0 else None,
        "average_gain": float(winning.mean()) if not winning.empty else 0.0,
        "average_loss": float(losing.mean()) if not losing.empty else 0.0,
        "exposure": float(pd.to_numeric(daily["gross_exposure"], errors="coerce").mean()),
        "average_trade_count": float(pd.to_numeric(daily["trade_count"], errors="coerce").mean()),
        "average_round_trip_turnover": float(pd.to_numeric(daily["round_trip_turnover"], errors="coerce").mean()),
        "gross_return_before_costs": float(gross_pnl.sum()),
        "total_cost_return": float(cost_return.sum()),
        "observations": observations,
        "elapsed_years": years,
        "start_date": start_date,
        "end_date": end_date,
    }
    metrics.update(_rolling_ratio_metrics(daily, risk_free_rate=risk_free_rate, periods_per_year=periods_per_year))

    return {key: _safe_float(value) if isinstance(value, (float, np.floating)) else value for key, value in metrics.items()}
