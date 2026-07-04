from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import pandas as pd

from nightfall_alpha.backtest.engine import BacktestConfig, BacktestResult, run_overnight_backtest
from nightfall_alpha.backtest.metrics import performance_metrics
from nightfall_alpha.config import Settings, load_settings
from nightfall_alpha.data.csv_provider import load_universe, save_price_file
from nightfall_alpha.data.schema import NUMERIC_PRICE_COLUMNS, PRICE_COLUMNS, normalize_symbol, validate_prices_frame
from nightfall_alpha.data.stooq_provider import StooqDownloadResult, download_stooq_daily_prices
from nightfall_alpha.data.synthetic import SyntheticMarketConfig, generate_synthetic_ohlcv
from nightfall_alpha.data.yahoo_provider import YahooDownloadResult, download_daily_prices, fetch_sp500_constituents
from nightfall_alpha.portfolio.optimizers import OptimizerSuiteSettings, build_portfolio_suite
from nightfall_alpha.portfolio.risk import overnight_return_matrix, prepare_optimization_matrix
from nightfall_alpha.strategy.overnight import OvernightEffectConfig, generate_signals


@dataclass(frozen=True)
class ResearchArtifacts:
    prices_path: Path
    signals_path: Path
    daily_path: Path
    equity_path: Path
    trades_path: Path
    metrics_path: Path
    portfolio_summary_path: Path
    portfolio_weights_path: Path


def artifact_paths(settings: Settings) -> ResearchArtifacts:
    data_dir = settings.project.data_dir
    processed = data_dir / "processed"
    reports = data_dir / "reports"
    processed.mkdir(parents=True, exist_ok=True)
    reports.mkdir(parents=True, exist_ok=True)
    return ResearchArtifacts(
        prices_path=processed / "prices.csv",
        signals_path=reports / "signals.csv",
        daily_path=reports / "daily.csv",
        equity_path=reports / "equity.csv",
        trades_path=reports / "trades.csv",
        metrics_path=reports / "metrics.json",
        portfolio_summary_path=reports / "portfolio_summary.csv",
        portfolio_weights_path=reports / "portfolio_weights.csv",
    )


def _read_price_cache_csv(path: Path) -> tuple[pd.DataFrame, bool]:
    try:
        return pd.read_csv(path), False
    except pd.errors.ParserError:
        return pd.read_csv(path, on_bad_lines="skip"), True


def load_price_cache(path: Path) -> pd.DataFrame:
    raw, repaired = _read_price_cache_csv(path)
    before = len(raw)
    raw = raw.loc[:, [column for column in PRICE_COLUMNS if column in raw.columns]].copy()
    raw = raw.dropna(subset=["date", "symbol"]).copy()
    raw["date"] = pd.to_datetime(raw["date"], errors="coerce", utc=False).dt.normalize()
    raw["symbol"] = raw["symbol"].map(normalize_symbol)
    for column in NUMERIC_PRICE_COLUMNS:
        if column in raw:
            raw[column] = pd.to_numeric(raw[column], errors="coerce")
    raw = raw.dropna(subset=["date", "symbol"])
    raw = raw[raw["date"] <= pd.Timestamp.today().normalize() + pd.Timedelta(days=5)]
    raw = raw.dropna(subset=[column for column in NUMERIC_PRICE_COLUMNS if column in raw.columns])
    raw = raw.drop_duplicates(["date", "symbol"], keep="last")
    prices = validate_prices_frame(raw)
    if repaired or len(prices) != before:
        prices.to_csv(path, index=False)
    return prices


def load_or_create_prices(
    settings: Settings | None = None,
    force: bool = False,
    symbols_limit: int | None = None,
    start: str = "2018-01-01",
    end: str = "2025-12-31",
) -> pd.DataFrame:
    cfg = settings or load_settings()
    paths = artifact_paths(cfg)

    if paths.prices_path.exists() and not force:
        return load_price_cache(paths.prices_path)

    universe_path = cfg.universe.live_file if cfg.universe.live_file.exists() else cfg.universe.sample_file
    universe = load_universe(universe_path)
    symbols = universe["symbol"].dropna().astype(str).tolist()
    if symbols_limit:
        symbols = symbols[:symbols_limit]
    if not symbols:
        raise ValueError(f"No symbols found in universe file: {universe_path}")

    prices = generate_synthetic_ohlcv(
        symbols,
        SyntheticMarketConfig(start=start, end=end, seed=cfg.project.seed),
    )
    save_price_file(prices, paths.prices_path)
    return prices


def download_real_market_data(
    settings: Settings | None = None,
    symbols: list[str] | None = None,
    start: str = "2015-01-01",
    end: str | None = None,
    symbols_limit: int | None = None,
    refresh_universe: bool = True,
    merge_existing: bool = False,
    source: str = "yahoo",
) -> YahooDownloadResult | StooqDownloadResult:
    cfg = settings or load_settings()
    paths = artifact_paths(cfg)

    if symbols:
        requested_symbols = symbols
    else:
        if refresh_universe or not cfg.universe.live_file.exists():
            try:
                universe = fetch_sp500_constituents()
                cfg.universe.live_file.parent.mkdir(parents=True, exist_ok=True)
                universe.to_csv(cfg.universe.live_file, index=False)
            except Exception:
                if cfg.universe.live_file.exists():
                    universe = load_universe(cfg.universe.live_file)
                elif cfg.universe.sample_file.exists():
                    universe = load_universe(cfg.universe.sample_file)
                else:
                    raise
        else:
            universe = load_universe(cfg.universe.live_file)
        requested_symbols = universe["symbol"].dropna().astype(str).tolist()

    if symbols_limit:
        requested_symbols = requested_symbols[:symbols_limit]

    if source == "stooq":
        result = download_stooq_daily_prices(requested_symbols, start=start, end=end)
    elif source == "yahoo_max":
        result = download_daily_prices(requested_symbols, start="1900-01-01", end=end)
    else:
        result = download_daily_prices(requested_symbols, start=start, end=end)
    prices = result.prices
    if merge_existing and paths.prices_path.exists():
        prices = merge_price_history(load_price_cache(paths.prices_path), result.prices)
    save_price_file(prices, paths.prices_path)
    return replace(result, prices=prices)


def merge_price_history(existing: pd.DataFrame, incoming: pd.DataFrame) -> pd.DataFrame:
    frames = [frame for frame in (existing, incoming) if frame is not None and not frame.empty]
    if not frames:
        return pd.DataFrame(columns=["date", "symbol", "open", "high", "low", "close", "volume"])

    merged = pd.concat(frames, ignore_index=True)
    merged = merged.copy()
    merged["date"] = pd.to_datetime(merged["date"], utc=False).dt.normalize()
    merged["symbol"] = merged["symbol"].map(normalize_symbol)
    merged = merged.drop_duplicates(["date", "symbol"], keep="last")
    return validate_prices_frame(merged)


def filter_price_history(
    prices: pd.DataFrame,
    start: str | None = None,
    end: str | None = None,
    symbols: list[str] | tuple[str, ...] | None = None,
) -> pd.DataFrame:
    filtered = prices.copy()
    filtered["date"] = pd.to_datetime(filtered["date"], errors="coerce").dt.normalize()
    if symbols:
        requested = {normalize_symbol(symbol) for symbol in symbols if str(symbol).strip()}
        filtered = filtered[filtered["symbol"].isin(requested)]
    if start:
        filtered = filtered[filtered["date"] >= pd.Timestamp(start).normalize()]
    if end:
        filtered = filtered[filtered["date"] <= pd.Timestamp(end).normalize()]
    if filtered.empty:
        raise ValueError("No price rows are available for the selected signal backtest data window.")
    return validate_prices_frame(filtered)


def ensure_price_history_for_symbols(
    settings: Settings | None,
    symbols: list[str] | tuple[str, ...],
    start: str = "2018-01-01",
    end: str | None = None,
    source: str = "yahoo",
    refresh_existing: bool = False,
) -> tuple[pd.DataFrame, list[str], list[str]]:
    cfg = settings or load_settings()
    paths = artifact_paths(cfg)
    requested = list(dict.fromkeys(normalize_symbol(symbol) for symbol in symbols if str(symbol).strip()))

    existing = load_price_cache(paths.prices_path) if paths.prices_path.exists() else pd.DataFrame()
    available = set(existing["symbol"].unique()) if not existing.empty else set()
    missing = [symbol for symbol in requested if symbol not in available]
    to_download = requested if refresh_existing else missing
    downloaded: list[str] = []

    if to_download:
        if source == "stooq":
            result = download_stooq_daily_prices(to_download, start=start, end=end)
        elif source == "yahoo_max":
            result = download_daily_prices(to_download, start="1900-01-01", end=end)
        else:
            result = download_daily_prices(to_download, start=start, end=end)
        downloaded = result.returned_symbols
        existing = merge_price_history(existing, result.prices)
        save_price_file(existing, paths.prices_path)

    return existing, missing, downloaded


def run_research_pipeline(
    settings: Settings | None = None,
    force_sample_prices: bool = False,
    symbols_limit: int | None = None,
    data_source: str = "existing",
    start: str = "2018-01-01",
    end: str | None = None,
    strategy_overrides: dict[str, Any] | None = None,
    price_start: str | None = None,
    price_end: str | None = None,
    price_symbols: list[str] | tuple[str, ...] | None = None,
    initial_capital: float | None = None,
    fees_bps: float | None = None,
    slippage_bps: float | None = None,
) -> dict[str, Any]:
    cfg = settings or load_settings()
    paths = artifact_paths(cfg)
    if data_source == "yfinance":
        download = download_real_market_data(
            cfg,
            start=start,
            end=end,
            symbols_limit=symbols_limit,
            refresh_universe=True,
            source="yahoo",
        )
        prices = download.prices
    elif data_source == "stooq":
        download = download_real_market_data(
            cfg,
            start=start,
            end=end,
            symbols_limit=symbols_limit,
            refresh_universe=True,
            source="stooq",
        )
        prices = download.prices
    elif data_source == "synthetic":
        prices = load_or_create_prices(cfg, force=True, symbols_limit=symbols_limit, start=start, end=end or "2025-12-31")
    else:
        prices = load_or_create_prices(cfg, force=force_sample_prices, symbols_limit=symbols_limit)

    prices = filter_price_history(prices, start=price_start, end=price_end, symbols=price_symbols)

    strategy_values = {
        "lookback_days": cfg.strategy.lookback_days,
        "min_history": cfg.strategy.min_history,
        "top_n": cfg.strategy.top_n,
        "max_weight": cfg.strategy.max_weight,
        "min_signal": cfg.strategy.min_signal,
    }
    for key, value in (strategy_overrides or {}).items():
        if key in strategy_values and value is not None:
            strategy_values[key] = value

    strategy_config = OvernightEffectConfig(
        lookback_days=int(strategy_values["lookback_days"]),
        min_history=int(strategy_values["min_history"]),
        top_n=int(strategy_values["top_n"]),
        max_weight=float(strategy_values["max_weight"]),
        min_signal=float(strategy_values["min_signal"]),
    )
    backtest_initial_capital = float(initial_capital if initial_capital is not None else cfg.backtest.initial_capital)
    backtest_fees_bps = float(fees_bps if fees_bps is not None else cfg.backtest.fees_bps)
    backtest_slippage_bps = float(slippage_bps if slippage_bps is not None else cfg.backtest.slippage_bps)
    backtest_config = BacktestConfig(
        initial_capital=backtest_initial_capital,
        fees_bps=backtest_fees_bps,
        slippage_bps=backtest_slippage_bps,
    )

    signals = generate_signals(prices, strategy_config)
    result = run_overnight_backtest(signals, backtest_config)
    metrics = performance_metrics(
        result.daily,
        initial_capital=backtest_initial_capital,
        risk_free_rate=cfg.portfolio.risk_free_rate,
    )
    metrics["backtest"] = {
        "initial_capital": backtest_initial_capital,
        "fees_bps": backtest_fees_bps,
        "slippage_bps": backtest_slippage_bps,
    }
    metrics["strategy"] = {
        "lookback_days": strategy_config.lookback_days,
        "min_history": strategy_config.min_history,
        "top_n": strategy_config.top_n,
        "max_weight": strategy_config.max_weight,
        "min_signal": strategy_config.min_signal,
    }
    metrics["data_window"] = {
        "start": prices["date"].min().strftime("%Y-%m-%d"),
        "end": prices["date"].max().strftime("%Y-%m-%d"),
        "symbol_count": int(prices["symbol"].nunique()),
        "row_count": int(len(prices)),
        "requested_start": price_start,
        "requested_end": price_end,
        "requested_symbol_count": int(len(price_symbols or [])),
        "requested_symbols": list(price_symbols or [])[:25],
    }

    returns, portfolio_matrix_metadata = prepare_optimization_matrix(
        overnight_return_matrix(prices),
        allow_symbol_filtering=True,
    )
    portfolio_max_weight = cfg.portfolio.max_weight
    portfolio_matrix_metadata["max_weight"] = portfolio_max_weight
    portfolio_summary, portfolio_weights = build_portfolio_suite(
        returns,
        max_weight=portfolio_max_weight,
        risk_free_rate=cfg.portfolio.risk_free_rate,
        initial_capital=backtest_initial_capital,
        optimizer_settings=OptimizerSuiteSettings(
            default_max_weight=portfolio_max_weight,
            cvar_alpha=cfg.portfolio.cvar_alpha,
        ),
        fees_bps=backtest_fees_bps,
        slippage_bps=backtest_slippage_bps,
    )
    metrics["portfolio_matrix"] = portfolio_matrix_metadata

    signals.to_csv(paths.signals_path, index=False)
    result.daily.to_csv(paths.daily_path, index=False)
    result.equity_curve.to_csv(paths.equity_path, index=False)
    result.trades.to_csv(paths.trades_path, index=False)
    portfolio_summary.to_csv(paths.portfolio_summary_path, index=False)
    portfolio_weights.to_csv(paths.portfolio_weights_path, index=False)

    with paths.metrics_path.open("w", encoding="utf-8") as handle:
        json.dump(metrics, handle, indent=2, default=str)

    return {
        "settings": cfg,
        "artifacts": paths,
        "prices": prices,
        "signals": signals,
        "backtest": result,
        "metrics": metrics,
        "strategy": metrics["strategy"],
        "data_window": metrics["data_window"],
        "portfolio_summary": portfolio_summary,
        "portfolio_weights": portfolio_weights,
    }


def ensure_reports(settings: Settings | None = None) -> ResearchArtifacts:
    cfg = settings or load_settings()
    paths = artifact_paths(cfg)
    required = [
        paths.daily_path,
        paths.equity_path,
        paths.metrics_path,
        paths.portfolio_summary_path,
        paths.portfolio_weights_path,
    ]
    if not all(path.exists() for path in required):
        run_research_pipeline(cfg)
    return paths


def load_metrics(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_report_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)
