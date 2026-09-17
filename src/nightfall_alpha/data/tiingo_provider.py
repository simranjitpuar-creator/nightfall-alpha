from __future__ import annotations

import json
import os
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

from nightfall_alpha.data.schema import normalize_symbol, validate_prices_frame
from nightfall_alpha.data.yahoo_provider import MarketDataProviderError

TIINGO_DAILY_URL = "https://api.tiingo.com/tiingo/daily/{symbol}/prices"


@dataclass(frozen=True)
class TiingoDownloadResult:
    prices: pd.DataFrame
    requested_symbols: list[str]
    returned_symbols: list[str]
    missing_symbols: list[str]
    start: str
    end: str | None


def resolve_tiingo_api_key(api_key: str | None = None, dotenv_path: Path | None = None) -> str:
    """Resolve the Tiingo API key from an explicit value, the environment, or .env."""
    if api_key and api_key.strip():
        return api_key.strip()
    env_value = os.environ.get("TIINGO_API_KEY", "").strip()
    if env_value:
        return env_value
    candidate = dotenv_path or Path.cwd() / ".env"
    if candidate.exists():
        for line in candidate.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and line.startswith("TIINGO_API_KEY="):
                value = line.split("=", 1)[1].strip().strip('"').strip("'")
                if value:
                    return value
    raise MarketDataProviderError(
        "Tiingo requires a free API key. Set TIINGO_API_KEY in your environment or .env file "
        "(sign up at https://www.tiingo.com -> Account -> API)."
    )


def _fetch_symbol_prices(
    symbol: str,
    start: str,
    end: str | None,
    api_key: str,
    timeout: float = 30.0,
) -> pd.DataFrame:
    query = {"startDate": start, "token": api_key}
    if end:
        query["endDate"] = end
    url = f"{TIINGO_DAILY_URL.format(symbol=symbol)}?{urlencode(query)}"
    request = Request(url, headers={"User-Agent": "nightfall-alpha/0.1", "Accept": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 404:
            return pd.DataFrame()
        if exc.code in {401, 403}:
            raise MarketDataProviderError(
                f"Tiingo rejected the API key (HTTP {exc.code}). Check TIINGO_API_KEY."
            ) from exc
        if exc.code == 429:
            raise MarketDataProviderError(
                "Tiingo rate limit reached (free tier: 500 requests/day, 20/second). "
                "Try again later or reduce the symbol count."
            ) from exc
        raise MarketDataProviderError(f"Tiingo request failed for {symbol} (HTTP {exc.code}).") from exc
    except URLError as exc:
        raise MarketDataProviderError(f"Tiingo request failed for {symbol}: {exc.reason}.") from exc

    if not isinstance(payload, list) or not payload:
        return pd.DataFrame()

    frame = pd.DataFrame(payload)
    frame["date"] = pd.to_datetime(frame["date"], utc=True).dt.tz_convert(None).dt.normalize()
    # Use split/dividend-adjusted series to match the Yahoo auto_adjust convention.
    # Drop the raw fields first so the rename cannot create duplicate columns.
    frame = frame.drop(columns=[c for c in ("open", "high", "low", "close", "volume") if c in frame.columns])
    frame = frame.rename(
        columns={
            "adjOpen": "open",
            "adjHigh": "high",
            "adjLow": "low",
            "adjClose": "close",
            "adjVolume": "volume",
        }
    )
    required = ["date", "open", "high", "low", "close", "volume"]
    if any(column not in frame.columns for column in required):
        return pd.DataFrame()
    frame["symbol"] = symbol
    return frame[["date", "symbol", "open", "high", "low", "close", "volume"]]


def download_tiingo_daily_prices(
    symbols: Sequence[str],
    start: str = "2015-01-01",
    end: str | None = None,
    api_key: str | None = None,
    pause_seconds: float = 0.05,
) -> TiingoDownloadResult:
    """Download adjusted daily bars from Tiingo's free EOD API (one request per symbol)."""
    requested = [normalize_symbol(symbol) for symbol in symbols if str(symbol).strip()]
    requested = list(dict.fromkeys(requested))
    if not requested:
        raise MarketDataProviderError("No symbols were supplied for Tiingo download.")

    key = resolve_tiingo_api_key(api_key)
    frames: list[pd.DataFrame] = []
    returned: list[str] = []
    missing: list[str] = []

    for position, symbol in enumerate(requested):
        frame = _fetch_symbol_prices(symbol, start=start, end=end, api_key=key)
        if frame.empty:
            missing.append(symbol)
        else:
            frames.append(frame)
            returned.append(symbol)
        if pause_seconds > 0 and position < len(requested) - 1:
            time.sleep(pause_seconds)

    if not frames:
        raise MarketDataProviderError("Tiingo returned no price rows for the requested symbols.")

    prices = validate_prices_frame(pd.concat(frames, ignore_index=True).dropna(subset=["open", "high", "low", "close"]))
    return TiingoDownloadResult(
        prices=prices,
        requested_symbols=requested,
        returned_symbols=sorted(returned),
        missing_symbols=missing,
        start=start,
        end=end,
    )
