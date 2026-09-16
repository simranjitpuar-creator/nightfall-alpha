from __future__ import annotations

from dataclasses import dataclass

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
    equity = float(cfg.initial_capital)
    cash_daily_rate = float(cfg.cash_rate) / 252.0
    daily_rows: list[dict[str, float | int | str | pd.Timestamp]] = []
    trade_rows: list[dict[str, float | int | str | pd.Timestamp]] = []

    for signal_date, positions in clean.groupby("signal_date", sort=True):
        start_equity = equity

        # Capacity: only part of the equity may be deployable; the rest sits in cash.
        if cfg.capital_capacity is not None and cfg.capital_capacity > 0:
            deployed = min(start_equity, float(cfg.capital_capacity))
        else:
            deployed = start_equity
        cash_weight_start = (start_equity - deployed) / start_equity if start_equity > 0 else 0.0

        # ADV participation: cap each position's notional at a fraction of its
        # average daily dollar volume. Excess weight is left un-invested.
        weights = positions["weight"].astype(float)
        if cfg.max_adv_participation and "adv_dollars" in positions and deployed > 0:
            caps = positions["adv_dollars"].fillna(0.0) * float(cfg.max_adv_participation) / deployed
            weights = pd.concat([weights, caps], axis=1).min(axis=1)

        gross_exposure = float(weights.abs().sum())
        gross_return = float((weights * positions["next_overnight_return"]).sum())
        cost_rate_bps = costs.rate_bps(signal_date)
        cost_return = float(2.0 * gross_exposure * cost_rate_bps / 10_000.0)
        net_return = gross_return - cost_return

        pnl = deployed * net_return
        cash_pnl = (start_equity - deployed) * cash_daily_rate
        equity = start_equity + pnl + cash_pnl
        # net_return is reported on total starting equity so metrics stay comparable.
        net_return_total = (pnl + cash_pnl) / start_equity if start_equity > 0 else 0.0
        exit_date = positions["exit_date"].max()
        trade_count = int(len(positions))

        daily_rows.append(
            {
                "signal_date": signal_date,
                "exit_date": exit_date,
                "starting_equity": start_equity,
                "ending_equity": equity,
                "gross_return": gross_return,
                "cost_return": cost_return,
                "net_return": net_return_total,
                "gross_exposure": gross_exposure,
                "round_trip_turnover": 2.0 * gross_exposure,
                "trade_count": trade_count,
                "cost_rate_bps": cost_rate_bps,
                "deployed_capital": deployed,
                "cash_weight": cash_weight_start,
            }
        )

        if gross_exposure > 0:
            cost_allocations = weights.abs() / gross_exposure * (deployed * cost_return)
        else:
            cost_allocations = weights.abs() * 0.0

        for ((_, row), weight, cost_dollars) in zip(positions.iterrows(), weights, cost_allocations, strict=False):
            notional = deployed * float(weight)
            gross_pnl = notional * float(row["next_overnight_return"])
            trade_rows.append(
                {
                    "signal_date": signal_date,
                    "exit_date": row["exit_date"],
                    "symbol": row["symbol"],
                    "weight": float(weight),
                    "overnight_return": float(row["next_overnight_return"]),
                    "notional": notional,
                    "gross_pnl": gross_pnl,
                    "cost": float(cost_dollars),
                    "net_pnl": gross_pnl - float(cost_dollars),
                    "signal_rank": int(row.get("signal_rank", 0)) if pd.notna(row.get("signal_rank", 0)) else 0,
                    "overnight_sharpe": float(row.get("overnight_sharpe", 0.0))
                    if pd.notna(row.get("overnight_sharpe", 0.0))
                    else 0.0,
                }
            )

    daily = pd.DataFrame(daily_rows)
    if daily.empty:
        equity_curve = pd.DataFrame(columns=["date", "equity", "drawdown"])
    else:
        equity_curve = daily[["exit_date", "ending_equity"]].rename(
            columns={"exit_date": "date", "ending_equity": "equity"}
        )
        rolling_peak = equity_curve["equity"].cummax()
        equity_curve["drawdown"] = equity_curve["equity"] / rolling_peak - 1.0

    trades = pd.DataFrame(trade_rows)
    return BacktestResult(daily=daily, trades=trades, equity_curve=equity_curve)
