from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class CostEra:
    """Approximate one-side trading cost (commissions/fees + half-spread/slippage) for a period."""

    start: pd.Timestamp
    fees_bps: float
    slippage_bps: float

    @property
    def total_bps(self) -> float:
        return self.fees_bps + self.slippage_bps


# Documented approximation of U.S. equity one-side costs by era. These are
# research-grade estimates, not vendor data; override per era in settings if
# you have better figures.
# - pre-May-1975: fixed commissions plus wide fractional (1/8) spreads
# - 1975 "May Day": negotiated commissions begin
# - 1990s: discount brokers, shrinking spreads
# - 1997: order-handling rules, 1/16 spreads
# - 2001: decimalization
# - 2007+: Reg NMS / ECN fragmentation, sub-penny spreads
# - 2015+: near-zero retail commissions, penny spreads on liquid names
DEFAULT_HISTORICAL_ERAS: tuple[CostEra, ...] = (
    CostEra(pd.Timestamp("1900-01-01"), fees_bps=30.0, slippage_bps=60.0),
    CostEra(pd.Timestamp("1975-05-01"), fees_bps=15.0, slippage_bps=40.0),
    CostEra(pd.Timestamp("1990-01-01"), fees_bps=8.0, slippage_bps=25.0),
    CostEra(pd.Timestamp("1997-01-01"), fees_bps=5.0, slippage_bps=15.0),
    CostEra(pd.Timestamp("2001-04-09"), fees_bps=2.0, slippage_bps=8.0),
    CostEra(pd.Timestamp("2007-01-01"), fees_bps=1.0, slippage_bps=3.0),
    CostEra(pd.Timestamp("2015-01-01"), fees_bps=0.5, slippage_bps=1.0),
)

COST_MODELS = ("flat", "historical")


def parse_cost_eras(rows: list[dict[str, object]] | None) -> tuple[CostEra, ...]:
    if not rows:
        return DEFAULT_HISTORICAL_ERAS
    eras = [
        CostEra(
            start=pd.Timestamp(str(row["start"])),
            fees_bps=float(row["fees_bps"]),
            slippage_bps=float(row["slippage_bps"]),
        )
        for row in rows
    ]
    eras.sort(key=lambda era: era.start)
    return tuple(eras)


@dataclass(frozen=True)
class CostModel:
    """Per-date trading cost lookup with a flat/historical toggle."""

    mode: str = "flat"
    flat_fees_bps: float = 0.5
    flat_slippage_bps: float = 1.0
    eras: tuple[CostEra, ...] = DEFAULT_HISTORICAL_ERAS

    def __post_init__(self) -> None:
        if self.mode not in COST_MODELS:
            raise ValueError(f"cost model must be one of {COST_MODELS}")

    def rate_bps(self, date: pd.Timestamp) -> float:
        """One-side cost in basis points for a trade on the given date."""
        if self.mode == "flat":
            return float(self.flat_fees_bps) + float(self.flat_slippage_bps)
        rate = self.eras[0].total_bps
        for era in self.eras:
            if pd.Timestamp(date) >= era.start:
                rate = era.total_bps
            else:
                break
        return float(rate)

    def rate_series(self, dates: pd.Series | pd.DatetimeIndex) -> pd.Series:
        index = pd.DatetimeIndex(pd.to_datetime(dates))
        values = [self.rate_bps(date) / 10_000.0 for date in index]
        return pd.Series(values, index=index, name="cost_rate_per_side")

    def describe(self) -> dict[str, object]:
        if self.mode == "flat":
            return {
                "mode": "flat",
                "fees_bps": float(self.flat_fees_bps),
                "slippage_bps": float(self.flat_slippage_bps),
            }
        return {
            "mode": "historical",
            "eras": [
                {"start": era.start.strftime("%Y-%m-%d"), "fees_bps": era.fees_bps, "slippage_bps": era.slippage_bps}
                for era in self.eras
            ],
        }
