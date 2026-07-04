from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class BacktestConfig:
    initial_capital: float = 1_000_000.0
    fees_bps: float = 0.5
    slippage_bps: float = 1.0


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
    clean = clean.sort_values(["signal_date", "symbol"]).reset_index(drop=True)

    equity = float(cfg.initial_capital)
    cost_per_side = (float(cfg.fees_bps) + float(cfg.slippage_bps)) / 10_000.0
    daily_rows: list[dict[str, float | int | str | pd.Timestamp]] = []
    trade_rows: list[dict[str, float | int | str | pd.Timestamp]] = []

    for signal_date, positions in clean.groupby("signal_date", sort=True):
        start_equity = equity
        gross_exposure = positions["weight"].abs().sum()
        gross_return = float((positions["weight"] * positions["next_overnight_return"]).sum())
        cost_return = float(2.0 * gross_exposure * cost_per_side)
        net_return = gross_return - cost_return
        equity = start_equity * (1.0 + net_return)
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
                "net_return": net_return,
                "gross_exposure": gross_exposure,
                "round_trip_turnover": 2.0 * gross_exposure,
                "trade_count": trade_count,
            }
        )

        if gross_exposure > 0:
            cost_allocations = positions["weight"].abs() / gross_exposure * (start_equity * cost_return)
        else:
            cost_allocations = positions["weight"].abs() * 0.0

        for (_, row), cost_dollars in zip(positions.iterrows(), cost_allocations, strict=False):
            gross_pnl = start_equity * float(row["weight"]) * float(row["next_overnight_return"])
            trade_rows.append(
                {
                    "signal_date": signal_date,
                    "exit_date": row["exit_date"],
                    "symbol": row["symbol"],
                    "weight": float(row["weight"]),
                    "overnight_return": float(row["next_overnight_return"]),
                    "notional": start_equity * float(row["weight"]),
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
