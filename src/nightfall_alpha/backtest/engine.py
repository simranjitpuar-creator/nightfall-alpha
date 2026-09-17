from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from nightfall_alpha.backtest.costs import DEFAULT_HISTORICAL_ERAS, CostModel, parse_cost_eras


@dataclass(frozen=True)
class BacktestConfig:
    initial_capital: float = 1_000_000.0
    fees_bps: float = 0.5
    slippage_bps: float = 1.0
    cost_model: str = "flat"  # "flat" uses fees_bps+slippage_bps; "historical" uses era table
    cost_eras: tuple | None = None  # optional override of the historical era table
    capital_capacity: float | None = None  # max deployable dollars; excess sits in cash
    cash_rate: float = 0.0  # annualized return earned on undeployed cash
    max_adv_participation: float | None = None  # cap per-symbol notional at this fraction of ADV

    def build_cost_model(self) -> CostModel:
        return CostModel(
            mode=self.cost_model,
            flat_fees_bps=self.fees_bps,
            flat_slippage_bps=self.slippage_bps,
            eras=parse_cost_eras(list(self.cost_eras)) if self.cost_eras else DEFAULT_HISTORICAL_ERAS,
        )


@dataclass(frozen=True)
class BacktestResult:
    daily: pd.DataFrame
    trades: pd.DataFrame
    equity_curve: pd.DataFrame


SIGNAL_COLUMNS = ["signal_date", "exit_date", "symbol", "weight", "next_overnight_return"]

TRADE_COLUMNS = [
    "signal_date",
    "exit_date",
    "symbol",
    "weight",
    "overnight_return",
    "notional",
    "gross_pnl",
    "cost",
    "net_pnl",
    "signal_rank",
    "overnight_sharpe",
]


def run_overnight_backtest(signals: pd.DataFrame, config: BacktestConfig | None = None) -> BacktestResult:
    cfg = config or BacktestConfig()
    missing = [column for column in SIGNAL_COLUMNS if column not in signals.columns]
    if missing:
        raise ValueError(f"signals missing columns: {', '.join(missing)}")

    clean = signals.copy()
    clean["signal_date"] = pd.to_datetime(clean["signal_date"]).dt.normalize()
    clean["exit_date"] = pd.to_datetime(clean["exit_date"]).dt.normalize()
    clean["weight"] = pd.to_numeric(clean["weight"], errors="coerce").fillna(0.0)
    clean["next_overnight_return"] = pd.to_numeric(clean["next_overnight_return"], errors="coerce").fillna(0.0)
    if "adv_dollars" in clean:
        clean["adv_dollars"] = pd.to_numeric(clean["adv_dollars"], errors="coerce")
    clean = clean.sort_values(["signal_date", "symbol"]).reset_index(drop=True)

    costs = cfg.build_cost_model()
    cash_daily_rate = float(cfg.cash_rate) / 252.0

    weights = clean["weight"].to_numpy(dtype=float)
    returns = clean["next_overnight_return"].to_numpy(dtype=float)
    adv = (
        clean["adv_dollars"].fillna(0.0).to_numpy(dtype=float)
        if "adv_dollars" in clean
        else np.zeros(len(clean), dtype=float)
    )
    day_values, day_starts = np.unique(clean["signal_date"].to_numpy(), return_index=True)
    day_ends = np.append(day_starts[1:], len(clean))
    n_days = len(day_values)
    cost_rates = np.array([costs.rate_bps(pd.Timestamp(date)) for date in day_values], dtype=float)

    # Single pass over days: apply capacity + ADV caps, aggregate, compound equity.
    capped_weights = np.empty(len(clean), dtype=float)
    deployed_per_trade = np.empty(len(clean), dtype=float)
    cost_per_trade_pool = np.empty(n_days, dtype=float)

    gross_returns = np.empty(n_days, dtype=float)
    gross_exposures = np.empty(n_days, dtype=float)
    trade_counts = np.empty(n_days, dtype=int)
    equity_path = np.empty(n_days, dtype=float)
    deployed_path = np.empty(n_days, dtype=float)
    net_return_path = np.empty(n_days, dtype=float)
    cost_return_path = np.empty(n_days, dtype=float)

    equity = float(cfg.initial_capital)
    for i in range(n_days):
        start, end = int(day_starts[i]), int(day_ends[i])
        start_equity = equity
        if cfg.capital_capacity is not None and cfg.capital_capacity > 0:
            deployed = min(start_equity, float(cfg.capital_capacity))
        else:
            deployed = start_equity

        day_weights = weights[start:end]
        if cfg.max_adv_participation and deployed > 0:
            caps = adv[start:end] * float(cfg.max_adv_participation) / deployed
            day_weights = np.minimum(day_weights, caps)
        capped_weights[start:end] = day_weights
        deployed_per_trade[start:end] = deployed

        exposure = float(np.abs(day_weights).sum())
        gross_return = float((day_weights * returns[start:end]).sum())
        cost_return = 2.0 * exposure * cost_rates[i] / 10_000.0

        gross_exposures[i] = exposure
        gross_returns[i] = gross_return
        trade_counts[i] = end - start
        cost_return_path[i] = cost_return
        cost_per_trade_pool[i] = deployed * cost_return
        deployed_path[i] = deployed

        pnl = deployed * (gross_return - cost_return)
        cash_pnl = (start_equity - deployed) * cash_daily_rate
        equity = start_equity + pnl + cash_pnl
        equity_path[i] = equity
        net_return_path[i] = (pnl + cash_pnl) / start_equity if start_equity > 0 else 0.0

    starting_equity = np.concatenate(([float(cfg.initial_capital)], equity_path[:-1]))
    daily = pd.DataFrame(
        {
            "signal_date": pd.to_datetime(day_values),
            "exit_date": clean.groupby("signal_date", sort=True)["exit_date"].max().to_numpy(),
            "starting_equity": starting_equity,
            "ending_equity": equity_path,
            "gross_return": gross_returns,
            "cost_return": cost_return_path,
            "net_return": net_return_path,
            "gross_exposure": gross_exposures,
            "round_trip_turnover": 2.0 * gross_exposures,
            "trade_count": trade_counts,
            "cost_rate_bps": cost_rates,
            "deployed_capital": deployed_path,
            "cash_weight": np.where(starting_equity > 0, (starting_equity - deployed_path) / starting_equity, 0.0),
        }
    )

    # Trade blotter (vectorized).
    if len(clean):
        trades = clean.copy()
        trades["weight"] = capped_weights
        trades["notional"] = deployed_per_trade * capped_weights
        trades["gross_pnl"] = trades["notional"] * returns
        day_index = np.repeat(np.arange(n_days), day_ends - day_starts)
        with np.errstate(divide="ignore", invalid="ignore"):
            cost_share = np.where(
                gross_exposures[day_index] > 0,
                np.abs(capped_weights) / gross_exposures[day_index],
                0.0,
            )
        trades["cost"] = cost_share * cost_per_trade_pool[day_index]
        trades["net_pnl"] = trades["gross_pnl"] - trades["cost"]
        trades = trades.rename(columns={"next_overnight_return": "overnight_return"})
        if "signal_rank" not in trades:
            trades["signal_rank"] = 0
        trades["signal_rank"] = trades["signal_rank"].fillna(0).astype(int)
        if "overnight_sharpe" not in trades:
            trades["overnight_sharpe"] = 0.0
        trades["overnight_sharpe"] = trades["overnight_sharpe"].fillna(0.0)
        trades = trades[TRADE_COLUMNS].reset_index(drop=True)
    else:
        trades = pd.DataFrame(columns=TRADE_COLUMNS)

    if daily.empty:
        equity_curve = pd.DataFrame(columns=["date", "equity", "drawdown"])
    else:
        equity_curve = daily[["exit_date", "ending_equity"]].rename(
            columns={"exit_date": "date", "ending_equity": "equity"}
        )
        rolling_peak = equity_curve["equity"].cummax()
        equity_curve["drawdown"] = equity_curve["equity"] / rolling_peak - 1.0

    return BacktestResult(daily=daily, trades=trades, equity_curve=equity_curve)
