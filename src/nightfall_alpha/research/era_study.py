"""Era-by-era survival study for the overnight-effect strategy.

Runs the standard signal + backtest stack once with the historical cost model,
then slices the daily return stream into cost eras. For each era it compounds
gross and net equity from a fresh starting stake, so the output shows both
whether the raw overnight edge existed in that period and whether it survived
that period's transaction costs — including how long a stake would have lasted.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from nightfall_alpha.backtest.costs import DEFAULT_HISTORICAL_ERAS
from nightfall_alpha.backtest.engine import BacktestConfig, run_overnight_backtest
from nightfall_alpha.config import Settings, load_settings
from nightfall_alpha.data.membership import apply_membership, load_membership, membership_path
from nightfall_alpha.data.pipeline import load_price_cache_for_settings, price_cache_exists
from nightfall_alpha.strategy.overnight import OvernightEffectConfig, generate_signals

TRADING_DAYS_PER_YEAR = 252

ERA_NAMES = {
    "1900-01-01": "Fixed commissions & wide spreads",
    "1975-05-01": "May Day: negotiated commissions",
    "1990-01-01": "Discount brokers",
    "1997-01-01": "Order-handling rules",
    "2001-04-09": "Decimalization",
    "2007-01-01": "Reg NMS / ECN fragmentation",
    "2015-01-01": "Near-zero commissions",
}


def era_windows(data_start: pd.Timestamp, data_end: pd.Timestamp) -> list[dict[str, Any]]:
    """Clip the historical cost eras to the available data window."""
    windows: list[dict[str, Any]] = []
    for index, era in enumerate(DEFAULT_HISTORICAL_ERAS):
        era_end = (
            DEFAULT_HISTORICAL_ERAS[index + 1].start - pd.Timedelta(days=1)
            if index + 1 < len(DEFAULT_HISTORICAL_ERAS)
            else data_end
        )
        start = max(era.start, data_start)
        end = min(era_end, data_end)
        if start > end:
            continue
        windows.append(
            {
                "key": era.start.strftime("%Y-%m-%d"),
                "name": ERA_NAMES.get(era.start.strftime("%Y-%m-%d"), "Era"),
                "start": start,
                "end": end,
                "fees_bps": era.fees_bps,
                "slippage_bps": era.slippage_bps,
                "cost_bps_per_side": era.total_bps,
            }
        )
    return windows


def _cagr(total_return: float, years: float) -> float | None:
    if years <= 0 or total_return <= -1:
        return None
    return (1.0 + total_return) ** (1.0 / years) - 1.0


def _max_drawdown(equity: pd.Series) -> float:
    running_max = equity.cummax()
    drawdown = equity / running_max - 1.0
    return float(drawdown.min()) if not drawdown.empty else 0.0


def _time_to_loss(equity: pd.Series, dates: pd.Series, fraction: float) -> dict[str, Any] | None:
    """First date/months at which equity falls to `fraction` of its starting value."""
    if equity.empty:
        return None
    threshold = float(equity.iloc[0]) * fraction
    breach = equity[equity <= threshold]
    if breach.empty:
        return None
    date = pd.Timestamp(dates.iloc[breach.index[0]] if breach.index[0] < len(dates) else dates.iloc[-1])
    months = round(int(breach.index[0] + 1) / 21.0, 1)
    return {"date": date.strftime("%Y-%m-%d"), "months": months}


def summarize_era(daily: pd.DataFrame, window: dict[str, Any], initial_capital: float) -> dict[str, Any]:
    """Compound gross and net equity for one era slice of the daily frame."""
    mask = (daily["signal_date"] >= window["start"]) & (daily["signal_date"] <= window["end"])
    era_daily = daily.loc[mask].sort_values("signal_date")
    if era_daily.empty:
        return {**{k: window[k] for k in ("key", "name", "fees_bps", "slippage_bps", "cost_bps_per_side")},
                "start": window["start"].strftime("%Y-%m-%d"), "end": window["end"].strftime("%Y-%m-%d"),
                "days": 0, "empty": True}

    dates = era_daily["signal_date"].reset_index(drop=True)
    gross_equity = initial_capital * (1.0 + era_daily["gross_return"].astype(float)).cumprod().reset_index(drop=True)
    net_equity = initial_capital * (1.0 + era_daily["net_return"].astype(float)).cumprod().reset_index(drop=True)
    net_returns = era_daily["net_return"].astype(float)

    days = int(len(era_daily))
    years = days / TRADING_DAYS_PER_YEAR
    net_total = float(net_equity.iloc[-1] / initial_capital - 1.0)
    gross_total = float(gross_equity.iloc[-1] / initial_capital - 1.0)
    mean = float(net_returns.mean())
    std = float(net_returns.std(ddof=1)) if days > 1 else 0.0
    sharpe = (mean / std) * (TRADING_DAYS_PER_YEAR**0.5) if std > 0 else None

    half = _time_to_loss(net_equity, dates, 0.5)
    ruin = _time_to_loss(net_equity, dates, 0.1)

    if ruin and ruin["months"] <= 12:
        verdict = "wipeout within a year"
    elif half and half["months"] <= 36:
        verdict = "capital bleeds out"
    elif net_total > 0:
        verdict = "edge survives costs"
    else:
        verdict = "slow bleed"

    return {
        "key": window["key"],
        "name": window["name"],
        "start": dates.iloc[0].strftime("%Y-%m-%d"),
        "end": dates.iloc[-1].strftime("%Y-%m-%d"),
        "days": days,
        "years": round(years, 1),
        "trades": int(era_daily["trade_count"].sum()),
        "fees_bps": window["fees_bps"],
        "slippage_bps": window["slippage_bps"],
        "cost_bps_per_side": window["cost_bps_per_side"],
        "gross_total_return": gross_total,
        "gross_cagr": _cagr(gross_total, years),
        "net_total_return": net_total,
        "net_cagr": _cagr(net_total, years),
        "net_final_equity": float(net_equity.iloc[-1]),
        "net_sharpe": sharpe,
        "net_max_drawdown": _max_drawdown(net_equity),
        "halved": half,
        "ruined": ruin,
        "verdict": verdict,
        "empty": False,
    }


def run_era_study(
    settings: Settings | None = None,
    initial_capital: float = 10_000.0,
    *,
    write: bool = True,
) -> dict[str, Any]:
    """Run the full-stack backtest with historical costs and slice it by cost era."""
    cfg = settings or load_settings()
    if not price_cache_exists(cfg):
        raise ValueError("No price cache found. Download market data first (System → Market Data).")

    prices = load_price_cache_for_settings(cfg)
    membership_file = membership_path(cfg.project.data_dir)
    if membership_file.exists():
        prices = apply_membership(prices, load_membership(membership_file))

    strategy_config = OvernightEffectConfig(
        lookback_days=cfg.strategy.lookback_days,
        min_history=cfg.strategy.min_history,
        top_n=cfg.strategy.top_n,
        max_weight=cfg.strategy.max_weight,
        min_signal=cfg.strategy.min_signal,
    )
    backtest_config = BacktestConfig(initial_capital=initial_capital, cost_model="historical")
    signals = generate_signals(prices, strategy_config)
    result = run_overnight_backtest(signals, backtest_config)

    daily = result.daily.copy()
    daily["signal_date"] = pd.to_datetime(daily["signal_date"])
    windows = era_windows(daily["signal_date"].min(), daily["signal_date"].max())
    eras = [summarize_era(daily, window, initial_capital) for window in windows]

    first_profitable = next((era for era in eras if not era.get("empty") and (era.get("net_total_return") or 0) > 0), None)
    conclusion = {
        "first_profitable_era": first_profitable["name"] if first_profitable else None,
        "first_profitable_start": first_profitable["start"] if first_profitable else None,
        "eras_tested": len([era for era in eras if not era.get("empty")]),
        "gross_edge_all_eras": all(
            (era.get("gross_total_return") or 0) > 0 for era in eras if not era.get("empty")
        ),
    }

    study: dict[str, Any] = {
        "generated_at": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
        "initial_capital": initial_capital,
        "cost_model": "historical",
        "strategy": {
            "lookback_days": strategy_config.lookback_days,
            "min_history": strategy_config.min_history,
            "top_n": strategy_config.top_n,
            "max_weight": strategy_config.max_weight,
            "min_signal": strategy_config.min_signal,
        },
        "data_window": {
            "start": daily["signal_date"].min().strftime("%Y-%m-%d"),
            "end": daily["signal_date"].max().strftime("%Y-%m-%d"),
        },
        "eras": eras,
        "conclusion": conclusion,
    }
    if write:
        path = era_study_path(cfg.project.data_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(study, indent=2), encoding="utf-8")
    return study


def era_study_path(data_dir: Path) -> Path:
    return data_dir / "reports" / "era_study.json"


def load_era_study(data_dir: Path) -> dict[str, Any] | None:
    path = era_study_path(data_dir)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
