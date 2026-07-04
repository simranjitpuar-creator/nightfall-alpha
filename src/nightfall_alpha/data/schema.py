from __future__ import annotations

from collections.abc import Iterable

import pandas as pd


PRICE_COLUMNS = ["date", "symbol", "open", "high", "low", "close", "volume"]
NUMERIC_PRICE_COLUMNS = ["open", "high", "low", "close", "volume"]


class DataValidationError(ValueError):
    """Raised when market data does not satisfy the expected OHLCV schema."""


def require_columns(frame: pd.DataFrame, columns: Iterable[str], name: str = "frame") -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise DataValidationError(f"{name} is missing required columns: {', '.join(missing)}")


def normalize_symbol(symbol: str) -> str:
    return str(symbol).strip().upper().replace(".", "-")


def validate_prices_frame(frame: pd.DataFrame) -> pd.DataFrame:
    require_columns(frame, PRICE_COLUMNS, "prices")
    prices = frame.copy()
    prices["date"] = pd.to_datetime(prices["date"], utc=False).dt.normalize()
    prices["symbol"] = prices["symbol"].map(normalize_symbol)

    for column in NUMERIC_PRICE_COLUMNS:
        prices[column] = pd.to_numeric(prices[column], errors="coerce")

    if prices[["date", "symbol"]].isna().any().any():
        raise DataValidationError("prices contains null date or symbol values")

    if prices[NUMERIC_PRICE_COLUMNS].isna().any().any():
        bad_columns = prices[NUMERIC_PRICE_COLUMNS].columns[prices[NUMERIC_PRICE_COLUMNS].isna().any()].tolist()
        raise DataValidationError(f"prices contains non-numeric values in: {', '.join(bad_columns)}")

    if (prices[["open", "high", "low", "close"]] <= 0).any().any():
        raise DataValidationError("OHLC prices must be positive")

    if (prices["volume"] < 0).any():
        raise DataValidationError("volume must be non-negative")

    duplicate_count = prices.duplicated(["date", "symbol"]).sum()
    if duplicate_count:
        raise DataValidationError(f"prices contains {duplicate_count} duplicate date/symbol rows")

    return prices.sort_values(["symbol", "date"]).reset_index(drop=True)


def read_prices_csv(path: str) -> pd.DataFrame:
    return validate_prices_frame(pd.read_csv(path))


def write_prices_csv(frame: pd.DataFrame, path: str) -> None:
    prices = validate_prices_frame(frame)
    prices.to_csv(path, index=False)
