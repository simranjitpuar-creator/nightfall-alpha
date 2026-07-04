from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

import pandas as pd

from nightfall_alpha.data.schema import normalize_symbol, validate_prices_frame


class StooqProviderError(RuntimeError):
    """Raised when Stooq cannot return usable price history."""


@dataclass(frozen=True)
class StooqDownloadResult:
    prices: pd.DataFrame
    requested_symbols: list[str]
    returned_symbols: list[str]
    missing_symbols: list[str]
    start: str
    end: str | None


def stooq_symbol(symbol: str) -> str:
    clean = normalize_symbol(symbol)
    if "." in clean:
        return clean
    return f"{clean}.US"


def _import_stooq_reader():
    try:
        import inspect
        import pandas.util._decorators as pandas_decorators

        signature = inspect.signature(pandas_decorators.deprecate_kwarg)
        first_parameter = next(iter(signature.parameters))
        if first_parameter == "klass":
            original = pandas_decorators.deprecate_kwarg

            def _compat_deprecate_kwarg(old_arg_name, new_arg_name=None, mapping=None, stacklevel=2):
                return original(
                    FutureWarning,
                    old_arg_name,
                    new_arg_name,
                    mapping=mapping,
                    stacklevel=stacklevel,
                )

            pandas_decorators.deprecate_kwarg = _compat_deprecate_kwarg

        from pandas_datareader.stooq import StooqDailyReader  # type: ignore
    except ImportError as exc:
        raise StooqProviderError(
            "pandas-datareader is not installed. Run `python -m pip install pandas-datareader`."
        ) from exc
    return StooqDailyReader


def _normalize_stooq_frame(frame: pd.DataFrame, symbol: str) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["date", "symbol", "open", "high", "low", "close", "volume"])

    normalized = frame.reset_index().rename(
        columns={
            "Date": "date",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        }
    )
    if "date" not in normalized.columns:
        normalized = normalized.rename(columns={normalized.columns[0]: "date"})
    normalized["symbol"] = symbol
    return normalized[["date", "symbol", "open", "high", "low", "close", "volume"]]


def download_stooq_daily_prices(
    symbols: Sequence[str],
    start: str = "1990-01-01",
    end: str | date | None = None,
) -> StooqDownloadResult:
    requested = [normalize_symbol(symbol) for symbol in symbols if str(symbol).strip()]
    requested = list(dict.fromkeys(requested))
    if not requested:
        raise StooqProviderError("No symbols were supplied for Stooq download.")

    StooqDailyReader = _import_stooq_reader()
    frames: list[pd.DataFrame] = []
    returned: list[str] = []
    end_date = pd.Timestamp(end) if end is not None else pd.Timestamp.today().normalize()

    for symbol in requested:
        try:
            raw = StooqDailyReader(symbols=stooq_symbol(symbol), start=start, end=end_date).read()
        except Exception:
            continue
        normalized = _normalize_stooq_frame(raw, symbol)
        if normalized.empty:
            continue
        frames.append(normalized)
        returned.append(symbol)

    if not frames:
        raise StooqProviderError("Stooq returned no price rows.")

    prices = validate_prices_frame(pd.concat(frames, ignore_index=True))
    returned = sorted(prices["symbol"].unique().tolist())
    missing = [symbol for symbol in requested if symbol not in set(returned)]
    return StooqDownloadResult(
        prices=prices,
        requested_symbols=requested,
        returned_symbols=returned,
        missing_symbols=missing,
        start=start,
        end=str(end) if end is not None else None,
    )
