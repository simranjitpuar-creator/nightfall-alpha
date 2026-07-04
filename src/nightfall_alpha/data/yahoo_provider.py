from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from io import StringIO
from urllib.request import Request, urlopen

import pandas as pd

from nightfall_alpha.data.schema import normalize_symbol, validate_prices_frame
from nightfall_alpha.paths import DATA_DIR


SP500_WIKIPEDIA_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"


class MarketDataProviderError(RuntimeError):
    """Raised when an external market data provider cannot return usable data."""


@dataclass(frozen=True)
class YahooDownloadResult:
    prices: pd.DataFrame
    requested_symbols: list[str]
    returned_symbols: list[str]
    missing_symbols: list[str]
    start: str
    end: str | None


def yahoo_symbol(symbol: str) -> str:
    return normalize_symbol(symbol)


def fetch_sp500_constituents() -> pd.DataFrame:
    request = Request(
        SP500_WIKIPEDIA_URL,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
            )
        },
    )
    with urlopen(request, timeout=20) as response:
        html = response.read().decode("utf-8", errors="replace")

    tables = pd.read_html(StringIO(html))
    if not tables:
        raise MarketDataProviderError("Could not read S&P 500 constituents from Wikipedia.")

    raw = tables[0].copy()
    columns = {column.lower().strip(): column for column in raw.columns}
    symbol_col = columns.get("symbol")
    name_col = columns.get("security")
    sector_col = columns.get("gics sector")
    if not symbol_col or not name_col:
        raise MarketDataProviderError("S&P 500 table does not contain expected Symbol/Security columns.")

    universe = pd.DataFrame(
        {
            "symbol": raw[symbol_col].map(yahoo_symbol),
            "name": raw[name_col].astype(str),
            "sector": raw[sector_col].astype(str) if sector_col else "",
        }
    )
    return universe.dropna(subset=["symbol"]).drop_duplicates("symbol").sort_values("symbol").reset_index(drop=True)


def _import_yfinance():
    try:
        import yfinance as yf  # type: ignore
    except ImportError as exc:
        raise MarketDataProviderError(
            "yfinance is not installed. Run `python -m pip install yfinance` or use the installed research environment."
        ) from exc
    cache_dir = DATA_DIR / "cache" / "yfinance"
    cache_dir.mkdir(parents=True, exist_ok=True)
    if hasattr(yf, "cache") and hasattr(yf.cache, "set_cache_location"):
        yf.cache.set_cache_location(str(cache_dir))
    elif hasattr(yf, "set_tz_cache_location"):
        yf.set_tz_cache_location(str(cache_dir))
    return yf


def _flatten_download(raw: pd.DataFrame, symbols: list[str]) -> pd.DataFrame:
    if raw.empty:
        return pd.DataFrame(columns=["date", "symbol", "open", "high", "low", "close", "volume"])

    frames: list[pd.DataFrame] = []
    field_map = {
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume",
    }

    if isinstance(raw.columns, pd.MultiIndex):
        first_level = set(str(value) for value in raw.columns.get_level_values(0))
        grouped_by_ticker = bool(set(symbols) & first_level)
        for symbol in symbols:
            if grouped_by_ticker:
                if symbol not in raw.columns.get_level_values(0):
                    continue
                frame = raw[symbol].copy()
            else:
                if symbol not in raw.columns.get_level_values(1):
                    continue
                frame = raw.xs(symbol, axis=1, level=1).copy()
            frame["symbol"] = symbol
            frames.append(frame)
    else:
        symbol = symbols[0] if symbols else ""
        frame = raw.copy()
        frame["symbol"] = symbol
        frames.append(frame)

    normalized: list[pd.DataFrame] = []
    for frame in frames:
        frame = frame.rename(columns=field_map)
        missing = [value for value in field_map.values() if value not in frame.columns]
        if missing:
            continue
        frame = frame.reset_index()
        date_column = "Date" if "Date" in frame.columns else frame.columns[0]
        frame = frame.rename(columns={date_column: "date"})
        normalized.append(frame[["date", "symbol", "open", "high", "low", "close", "volume"]])

    if not normalized:
        return pd.DataFrame(columns=["date", "symbol", "open", "high", "low", "close", "volume"])

    return pd.concat(normalized, ignore_index=True)


def download_daily_prices(
    symbols: Sequence[str],
    start: str = "2015-01-01",
    end: str | date | None = None,
    auto_adjust: bool = True,
) -> YahooDownloadResult:
    requested = [yahoo_symbol(symbol) for symbol in symbols if str(symbol).strip()]
    requested = list(dict.fromkeys(requested))
    if not requested:
        raise MarketDataProviderError("No symbols were supplied for Yahoo Finance download.")

    yf = _import_yfinance()
    raw = yf.download(
        tickers=requested,
        start=start,
        end=end,
        auto_adjust=auto_adjust,
        group_by="ticker",
        threads=True,
        progress=False,
    )
    flat = _flatten_download(raw, requested)
    if flat.empty:
        raise MarketDataProviderError("Yahoo Finance returned no price rows.")

    prices = validate_prices_frame(flat.dropna(subset=["open", "high", "low", "close"]))
    returned = sorted(prices["symbol"].unique().tolist())
    missing = [symbol for symbol in requested if symbol not in set(returned)]
    return YahooDownloadResult(
        prices=prices,
        requested_symbols=requested,
        returned_symbols=returned,
        missing_symbols=missing,
        start=start,
        end=str(end) if end is not None else None,
    )
