from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import pandas as pd


@dataclass(frozen=True)
class OrderIntent:
    symbol: str
    target_weight: float
    reason: str


@dataclass(frozen=True)
class ExecutionReport:
    symbol: str
    requested_weight: float
    status: str
    message: str


class BrokerAdapter(Protocol):
    def place_target_weight_orders(self, orders: list[OrderIntent]) -> list[ExecutionReport]:
        """Place target-weight orders and return execution reports."""


class DryRunBroker:
    """Records intended trades without submitting orders."""

    def place_target_weight_orders(self, orders: list[OrderIntent]) -> list[ExecutionReport]:
        return [
            ExecutionReport(
                symbol=order.symbol,
                requested_weight=order.target_weight,
                status="dry_run",
                message=f"Would target {order.target_weight:.2%}: {order.reason}",
            )
            for order in orders
        ]


def weights_to_order_intents(weights: pd.DataFrame, reason: str = "overnight_effect") -> list[OrderIntent]:
    required = {"symbol", "weight"}
    missing = required - set(weights.columns)
    if missing:
        raise ValueError(f"weights missing columns: {', '.join(sorted(missing))}")
    return [
        OrderIntent(symbol=str(row.symbol), target_weight=float(row.weight), reason=reason)
        for row in weights.itertuples(index=False)
        if abs(float(row.weight)) > 1e-6
    ]
