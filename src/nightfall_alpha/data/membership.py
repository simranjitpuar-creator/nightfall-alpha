"""Point-in-time index membership handling.

Backtests that apply today's S&P 500 constituents to decades of history carry
survivorship bias: delisted/removed names vanish and every member is treated
as if it was always in the index. This module supports an optional
point-in-time membership file that masks prices to the periods when each
symbol was actually in the index:

    data/universe/sp500_membership.csv

Columns:
    symbol,start_date,end_date

`end_date` may be empty for symbols still in the index. Multiple rows per
symbol are allowed for repeated inclusion spells.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from nightfall_alpha.data.schema import normalize_symbol

MEMBERSHIP_FILENAME = "sp500_membership.csv"

SURVIVORSHIP_WARNING = (
    "Backtest uses today's index constituents applied to historical prices "
    "(no point-in-time membership file found at data/universe/sp500_membership.csv). "
    "Results before a symbol's actual index inclusion carry survivorship bias and "
    "delisted names are missing entirely."
)


def membership_path(data_dir: Path) -> Path:
    return Path(data_dir) / "universe" / MEMBERSHIP_FILENAME


def load_membership(path: str | Path) -> pd.DataFrame:
    membership = pd.read_csv(Path(path))
    required = {"symbol", "start_date", "end_date"}
    missing = required - set(membership.columns)
    if missing:
        raise ValueError(f"membership file missing columns: {', '.join(sorted(missing))}")
    membership = membership.copy()
    membership["symbol"] = membership["symbol"].map(normalize_symbol)
    membership["start_date"] = pd.to_datetime(membership["start_date"], errors="coerce")
    membership["end_date"] = pd.to_datetime(membership["end_date"], errors="coerce")
    membership = membership.dropna(subset=["symbol", "start_date"])
    return membership.reset_index(drop=True)


def apply_membership(prices: pd.DataFrame, membership: pd.DataFrame) -> pd.DataFrame:
    """Keep only price rows where the symbol was an index member on that date."""
    if prices.empty or membership.empty:
        return prices

    prices = prices.copy()
    prices["_row_order"] = range(len(prices))
    merged = prices.merge(membership, on="symbol", how="inner")
    in_window = (merged["date"] >= merged["start_date"]) & (
        merged["end_date"].isna() | (merged["date"] <= merged["end_date"])
    )
    kept = merged[in_window].drop_duplicates("_row_order")
    kept = kept.sort_values("_row_order")
    return kept[prices.columns.drop("_row_order")].reset_index(drop=True)


def membership_summary(prices: pd.DataFrame, membership: pd.DataFrame | None) -> dict[str, object]:
    symbols = int(prices["symbol"].nunique()) if not prices.empty else 0
    if membership is None:
        return {
            "point_in_time": False,
            "warning": SURVIVORSHIP_WARNING,
            "membership_symbols": 0,
            "price_symbols": symbols,
        }
    member_symbols = set(membership["symbol"].unique())
    missing = sorted(set(prices["symbol"].unique()) - member_symbols) if not prices.empty else []
    return {
        "point_in_time": True,
        "warning": None if not missing else f"{len(missing)} price symbols have no membership rows and were excluded.",
        "membership_symbols": len(member_symbols),
        "price_symbols": symbols,
        "symbols_without_membership": missing[:50],
    }
