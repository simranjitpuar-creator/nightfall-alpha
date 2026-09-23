from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import pandas as pd

from nightfall_alpha.config import Settings, load_settings
from nightfall_alpha.data.csv_provider import load_universe
from nightfall_alpha.data.schema import normalize_symbol

SECTOR_ETF_CODES = {
    "Communication Services": "XLC",
    "Consumer Discretionary": "XLY",
    "Consumer Staples": "XLP",
    "Energy": "XLE",
    "Financials": "XLF",
    "Health Care": "XLV",
    "Industrials": "XLI",
    "Information Technology": "XLK",
    "Materials": "XLB",
    "Real Estate": "XLRE",
    "Utilities": "XLU",
}


def _metadata_path(settings: Settings) -> Path:
    return settings.project.data_dir / "universe" / "metadata.csv"


def _price_symbols(settings: Settings) -> list[str]:
    processed = settings.project.data_dir / "processed"
    parquet_path = processed / "prices.parquet"
    csv_path = processed / "prices.csv"
    if parquet_path.exists():
        prices = pd.read_parquet(parquet_path, columns=["symbol"])
    elif csv_path.exists():
        prices = pd.read_csv(csv_path, usecols=["symbol"])
    else:
        return []
    return sorted(prices["symbol"].dropna().map(normalize_symbol).unique().tolist())


def _base_universe(settings: Settings) -> pd.DataFrame:
    if settings.universe.live_file.exists():
        universe = load_universe(settings.universe.live_file)
    elif settings.universe.sample_file.exists():
        universe = load_universe(settings.universe.sample_file)
    else:
        universe = pd.DataFrame(columns=["symbol", "name", "sector"])

    if "name" not in universe.columns:
        universe["name"] = universe["symbol"]
    if "sector" not in universe.columns:
        universe["sector"] = "Unclassified"
    return universe[["symbol", "name", "sector"]].copy()


def _market_cap_from_fast_info(ticker: Any) -> float | None:
    try:
        value = ticker.fast_info.get("market_cap")
    except Exception:
        value = None
    if value is None:
        try:
            value = ticker.info.get("marketCap")
        except Exception:
            value = None
    try:
        return float(value) if value else None
    except (TypeError, ValueError):
        return None


def fetch_market_caps(symbols: list[str]) -> dict[str, float | None]:
    if not symbols:
        return {}
    try:
        import yfinance as yf  # type: ignore
    except ImportError:
        return {symbol: None for symbol in symbols}

    caps: dict[str, float | None] = {}
    for symbol in symbols:
        try:
            caps[symbol] = _market_cap_from_fast_info(yf.Ticker(symbol))
        except Exception:
            caps[symbol] = None
    return caps


# Assembling metadata is expensive (it scans the full price cache for symbols),
# so cache the result keyed on the mtimes of every input file. Market-cap
# refreshes always bypass the cache because they fetch live data.
_METADATA_CACHE: dict[str, Any] = {"signature": None, "frame": None}
_METADATA_LOCK = threading.Lock()


def _metadata_signature(cfg: Settings) -> tuple[Any, ...]:
    processed = cfg.project.data_dir / "processed"
    inputs = (
        _metadata_path(cfg),
        cfg.universe.live_file,
        cfg.universe.sample_file,
        processed / "prices.parquet",
        processed / "prices.csv",
    )
    return tuple(path.stat().st_mtime_ns if path.exists() else None for path in inputs)


def load_universe_metadata(
    settings: Settings | None = None,
    refresh_market_caps: bool = False,
    cap_limit: int = 75,
) -> pd.DataFrame:
    cfg = settings or load_settings()
    if not refresh_market_caps:
        signature = _metadata_signature(cfg)
        cached = _METADATA_CACHE.get("frame")
        if isinstance(cached, pd.DataFrame) and _METADATA_CACHE.get("signature") == signature:
            return cached.copy()
        with _METADATA_LOCK:
            cached = _METADATA_CACHE.get("frame")
            if isinstance(cached, pd.DataFrame) and _METADATA_CACHE.get("signature") == signature:
                return cached.copy()
            frame = _build_universe_metadata(cfg, refresh_market_caps=False, cap_limit=cap_limit)
            # The build rewrites metadata.csv, which bumps its mtime — store the
            # post-build signature or the cache invalidates itself on every call.
            _METADATA_CACHE["signature"] = _metadata_signature(cfg)
            _METADATA_CACHE["frame"] = frame
            return frame.copy()
    return _build_universe_metadata(cfg, refresh_market_caps=True, cap_limit=cap_limit)


def _build_universe_metadata(
    cfg: Settings,
    refresh_market_caps: bool = False,
    cap_limit: int = 75,
) -> pd.DataFrame:
    metadata_path = _metadata_path(cfg)
    base = _base_universe(cfg)
    cached_symbols = _price_symbols(cfg)

    if metadata_path.exists():
        existing = pd.read_csv(metadata_path)
    else:
        existing = pd.DataFrame(columns=["symbol", "name", "sector", "sector_code", "market_cap", "in_price_cache"])

    base["symbol"] = base["symbol"].map(normalize_symbol)
    if "symbol" in existing.columns:
        existing = existing.copy()
        existing["symbol"] = existing["symbol"].map(normalize_symbol)
    else:
        existing = pd.DataFrame(columns=["symbol", "market_cap"])
    existing_caps = existing[["symbol", "market_cap"]].dropna(subset=["symbol"]) if "market_cap" in existing.columns else pd.DataFrame(columns=["symbol", "market_cap"])
    metadata = base.merge(existing_caps, on="symbol", how="outer")
    if cached_symbols:
        metadata = pd.concat([metadata, pd.DataFrame({"symbol": cached_symbols})], ignore_index=True, sort=False)
    metadata["symbol"] = metadata["symbol"].map(normalize_symbol)
    metadata = metadata.dropna(subset=["symbol"]).drop_duplicates("symbol", keep="first")
    metadata["name"] = metadata["name"].fillna(metadata["symbol"])
    metadata["sector"] = metadata["sector"].fillna("Unclassified")
    metadata["sector_code"] = metadata["sector"].map(SECTOR_ETF_CODES).fillna("OTHER")
    metadata["in_price_cache"] = metadata["symbol"].isin(set(cached_symbols))
    metadata["market_cap"] = pd.to_numeric(metadata.get("market_cap"), errors="coerce")

    if refresh_market_caps:
        needs = metadata[metadata["market_cap"].isna()].copy()
        needs["cache_rank"] = needs["symbol"].isin(set(cached_symbols)).astype(int)
        needs_caps = needs.sort_values(["cache_rank", "symbol"], ascending=[False, True])["symbol"].head(cap_limit).tolist()
        caps = fetch_market_caps(needs_caps)
        if caps:
            for symbol, cap in caps.items():
                metadata.loc[metadata["symbol"] == symbol, "market_cap"] = cap

    metadata = metadata.sort_values(
        ["sector_code", "market_cap", "symbol"],
        ascending=[True, False, True],
        na_position="last",
    ).reset_index(drop=True)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata.to_csv(metadata_path, index=False)
    return metadata
