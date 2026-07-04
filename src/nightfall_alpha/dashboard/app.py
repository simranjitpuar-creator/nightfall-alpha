from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from nightfall_alpha.config import Settings, load_settings
from nightfall_alpha.data.pipeline import (
    artifact_paths,
    download_real_market_data,
    ensure_reports,
    ensure_price_history_for_symbols,
    load_metrics,
    load_or_create_prices,
    load_report_csv,
    run_research_pipeline,
)
from nightfall_alpha.data.universe_metadata import load_universe_metadata
from nightfall_alpha.portfolio.builder import PortfolioBuildSpec, build_custom_portfolio, parse_symbols
from nightfall_alpha.portfolio.optimizers import OptimizerSuiteSettings


STATIC_DIR = Path(__file__).resolve().parent / "static"


class SignalSettingsRequest(BaseModel):
    lookback_days: int = Field(default=63, ge=2)
    min_history: int = Field(default=40, ge=1)
    top_n: int = Field(default=25, ge=1, le=505)
    max_weight: float = Field(default=0.07, gt=0.0, le=1.0)
    min_signal: float = 0.0
    initial_capital: float = Field(default=1_000_000.0, gt=0.0)
    fees_bps: float = Field(default=0.5, ge=0.0)
    slippage_bps: float = Field(default=1.0, ge=0.0)


class SignalBacktestRequest(SignalSettingsRequest):
    force_sample_prices: bool = False
    price_start: str | None = None
    price_end: str | None = None
    price_symbols: str | list[str] | None = None


class MarketDataRequest(BaseModel):
    tickers: str | None = Field(default=None, description="Comma or space-separated tickers. Omit for S&P 500.")
    source: str = "yahoo"
    start: str = "2018-01-01"
    end: str | None = None
    symbols_limit: int | None = Field(default=None, ge=1, le=505)
    run_backtest: bool = True
    strategy: SignalSettingsRequest | None = None


class PortfolioBuilderRequest(BaseModel):
    symbols: str | list[str] | None = None
    use_entire_universe: bool = False
    method: str = "best"
    return_model: str = "overnight"
    rebalance_frequency: str = "none"
    initial_capital: float = Field(default=1_000_000.0, gt=0.0)
    fees_bps: float = Field(default=0.0, ge=0.0)
    slippage_bps: float = Field(default=0.0, ge=0.0)
    max_weight: float = Field(default=0.12, ge=0.0, le=1.0)
    kelly_fraction: float = Field(default=0.5, ge=0.0, le=1.0)
    kelly_max_weight: float | None = Field(default=None, ge=0.0, le=1.0)
    mean_variance_risk_aversion: float = Field(default=8.0, gt=0.0)
    mean_variance_max_weight: float | None = Field(default=None, ge=0.0, le=1.0)
    minimum_variance_max_weight: float | None = Field(default=None, ge=0.0, le=1.0)
    inverse_volatility_max_weight: float | None = Field(default=None, ge=0.0, le=1.0)
    cvar_alpha: float = Field(default=0.95, gt=0.5, lt=1.0)
    cvar_max_weight: float | None = Field(default=None, ge=0.0, le=1.0)
    black_litterman_tau: float = Field(default=0.05, gt=0.0)
    black_litterman_prior_risk_aversion: float = Field(default=2.5, gt=0.0)
    black_litterman_risk_aversion: float = Field(default=8.0, gt=0.0)
    black_litterman_max_weight: float | None = Field(default=None, ge=0.0, le=1.0)
    lookback_days: int | None = Field(default=756, ge=20)
    auto_download_missing: bool = True
    refresh_history: bool = False
    data_start: str = "2018-01-01"
    data_source: str = "yahoo"


def _effective_portfolio_lookback(request: PortfolioBuilderRequest) -> int | None:
    return request.lookback_days


def _should_refresh_portfolio_history(request: PortfolioBuilderRequest) -> bool:
    return bool(request.refresh_history)


def _missing_symbols_from_prices(prices: pd.DataFrame, symbols: tuple[str, ...]) -> list[str]:
    if not symbols or prices.empty or "symbol" not in prices:
        return list(symbols)
    available = set(prices["symbol"].dropna().astype(str).unique())
    return [symbol for symbol in symbols if symbol not in available]


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    clean = frame.copy()
    for column in clean.columns:
        if "date" in column:
            clean[column] = pd.to_datetime(clean[column], errors="coerce").dt.strftime("%Y-%m-%d")
    clean = clean.where(pd.notna(clean), None)
    return clean.to_dict(orient="records")


def _date_column(frame: pd.DataFrame) -> str | None:
    for column in ("exit_date", "signal_date", "date"):
        if column in frame.columns:
            return column
    return None


def _filter_trades_frame(
    frame: pd.DataFrame,
    *,
    start: str | None = None,
    end: str | None = None,
    symbol: str | None = None,
    pnl: str = "all",
) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    filtered = frame.copy()
    date_column = _date_column(filtered)
    if date_column:
        dates = pd.to_datetime(filtered[date_column], errors="coerce")
        if start:
            filtered = filtered[dates >= pd.Timestamp(start)]
            dates = pd.to_datetime(filtered[date_column], errors="coerce")
        if end:
            filtered = filtered[dates <= pd.Timestamp(end)]
    if symbol and "symbol" in filtered:
        query = symbol.strip().upper()
        if query:
            filtered = filtered[filtered["symbol"].astype(str).str.upper().str.contains(query, regex=False)]
    if pnl in {"wins", "losses"} and "net_pnl" in filtered:
        net_pnl = pd.to_numeric(filtered["net_pnl"], errors="coerce")
        filtered = filtered[net_pnl > 0] if pnl == "wins" else filtered[net_pnl < 0]
    return filtered


def _date_bounds(frame: pd.DataFrame, preferred: str | None = None) -> tuple[str | None, str | None]:
    if frame.empty:
        return None, None
    columns = [preferred] if preferred else []
    columns.extend(["exit_date", "signal_date", "date"])
    for column in dict.fromkeys(column for column in columns if column):
        if column in frame:
            dates = pd.to_datetime(frame[column], errors="coerce").dropna()
            if not dates.empty:
                return dates.min().strftime("%Y-%m-%d"), dates.max().strftime("%Y-%m-%d")
    return None, None


def _trade_summary(source: pd.DataFrame, filtered: pd.DataFrame, returned: pd.DataFrame) -> dict[str, Any]:
    source_start, source_end = _date_bounds(source)
    filtered_start, filtered_end = _date_bounds(filtered)
    summary: dict[str, Any] = {
        "source_total_trades": int(len(source)),
        "source_symbols": int(source["symbol"].nunique()) if not source.empty and "symbol" in source else 0,
        "source_start_date": source_start,
        "source_end_date": source_end,
        "filtered_trades": int(len(filtered)),
        "returned_trades": int(len(returned)),
        "filtered_symbols": int(filtered["symbol"].nunique()) if not filtered.empty and "symbol" in filtered else 0,
        "filtered_start_date": filtered_start,
        "filtered_end_date": filtered_end,
        "latest_entry_date": None,
        "latest_exit_date": None,
        "latest_trade_count": 0,
        "total_net_pnl": 0.0,
        "total_gross_pnl": 0.0,
        "total_cost": 0.0,
        "total_notional": 0.0,
        "average_weight": None,
        "win_rate": None,
        "average_trade_pnl": None,
        "best_trade_pnl": None,
        "worst_trade_pnl": None,
    }
    summary.update(
        {
            "total_trades": summary["source_total_trades"],
            "shown_trades": summary["returned_trades"],
            "symbols": summary["filtered_symbols"],
            "start_date": summary["source_start_date"],
            "end_date": summary["source_end_date"],
        }
    )
    if filtered.empty:
        return summary

    dated = filtered.copy()
    for column in ("signal_date", "exit_date"):
        if column in dated:
            dated[column] = pd.to_datetime(dated[column], errors="coerce")
    if "signal_date" in dated and dated["signal_date"].notna().any():
        summary["latest_entry_date"] = dated["signal_date"].max().strftime("%Y-%m-%d")
    if "exit_date" in dated and dated["exit_date"].notna().any():
        latest_exit = dated["exit_date"].max()
        summary["latest_exit_date"] = latest_exit.strftime("%Y-%m-%d")
        summary["latest_trade_count"] = int((dated["exit_date"] == latest_exit).sum())

    numeric = {
        column: pd.to_numeric(filtered.get(column, pd.Series(dtype=float)), errors="coerce")
        for column in ("net_pnl", "gross_pnl", "cost", "notional", "weight")
    }
    net_pnl = numeric["net_pnl"].dropna()
    summary["total_net_pnl"] = float(numeric["net_pnl"].sum(skipna=True))
    summary["total_gross_pnl"] = float(numeric["gross_pnl"].sum(skipna=True))
    summary["total_cost"] = float(numeric["cost"].sum(skipna=True))
    summary["total_notional"] = float(numeric["notional"].sum(skipna=True))
    summary["average_weight"] = float(numeric["weight"].mean(skipna=True)) if numeric["weight"].notna().any() else None
    summary["win_rate"] = float((net_pnl > 0).mean()) if not net_pnl.empty else None
    summary["average_trade_pnl"] = float(net_pnl.mean()) if not net_pnl.empty else None
    summary["best_trade_pnl"] = float(net_pnl.max()) if not net_pnl.empty else None
    summary["worst_trade_pnl"] = float(net_pnl.min()) if not net_pnl.empty else None
    return summary


def _csv_response(frame: pd.DataFrame, filename: str) -> Response:
    content = frame.where(pd.notna(frame), "").to_csv(index=False)
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _load_payload(settings: Settings) -> dict[str, Any]:
    paths = ensure_reports(settings)
    metrics = load_metrics(paths.metrics_path)
    daily = load_report_csv(paths.daily_path)
    equity = load_report_csv(paths.equity_path)
    trades = load_report_csv(paths.trades_path)
    portfolio_summary = load_report_csv(paths.portfolio_summary_path)
    portfolio_weights = load_report_csv(paths.portfolio_weights_path)
    signals = load_report_csv(paths.signals_path)

    if not portfolio_summary.empty and not portfolio_weights.empty and "portfolio" in portfolio_weights:
        weights = portfolio_weights.copy()
        weights["weight"] = pd.to_numeric(weights.get("weight", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
        exposure = weights.groupby("portfolio")["weight"].agg(
            weight_sum="sum",
            gross_exposure=lambda values: values.abs().sum(),
            max_weight="max",
        )
        exposure["cash_weight"] = (1.0 - exposure["weight_sum"]).clip(lower=0.0)
        portfolio_summary = portfolio_summary.merge(
            exposure.reset_index(),
            on="portfolio",
            how="left",
            suffixes=("", "_from_weights"),
        )
        for column in ("weight_sum", "gross_exposure", "cash_weight", "max_weight"):
            fallback = f"{column}_from_weights"
            if fallback in portfolio_summary:
                if column in portfolio_summary:
                    portfolio_summary[column] = portfolio_summary[column].fillna(portfolio_summary[fallback])
                else:
                    portfolio_summary[column] = portfolio_summary[fallback]
                portfolio_summary = portfolio_summary.drop(columns=[fallback])

    latest_signal_date = None
    latest_holdings = pd.DataFrame()
    if not signals.empty:
        signals["signal_date"] = pd.to_datetime(signals["signal_date"], errors="coerce")
        latest_signal_date = signals["signal_date"].max()
        latest_holdings = signals[signals["signal_date"] == latest_signal_date].sort_values("weight", ascending=False)
        try:
            metadata = load_universe_metadata(settings, refresh_market_caps=False)[
                ["symbol", "name", "sector", "sector_code", "market_cap"]
            ]
            latest_holdings = latest_holdings.merge(metadata, on="symbol", how="left")
        except Exception:
            latest_holdings = latest_holdings.copy()

    strategy = metrics.get("strategy") if isinstance(metrics.get("strategy"), dict) else {}
    backtest = metrics.get("backtest") if isinstance(metrics.get("backtest"), dict) else {}
    data_window = metrics.get("data_window") if isinstance(metrics.get("data_window"), dict) else {}
    strategy_context = {
        "lookback_days": int(strategy.get("lookback_days", settings.strategy.lookback_days)),
        "min_history": int(strategy.get("min_history", settings.strategy.min_history)),
        "top_n": int(strategy.get("top_n", settings.strategy.top_n)),
        "max_weight": float(strategy.get("max_weight", settings.strategy.max_weight)),
        "min_signal": float(strategy.get("min_signal", settings.strategy.min_signal)),
    }
    backtest_context = {
        "initial_capital": float(
            backtest.get("initial_capital", metrics.get("initial_capital", settings.backtest.initial_capital))
        ),
        "fees_bps": float(backtest.get("fees_bps", settings.backtest.fees_bps)),
        "slippage_bps": float(backtest.get("slippage_bps", settings.backtest.slippage_bps)),
    }

    return {
        "metrics": metrics,
        "daily": daily,
        "equity": equity,
        "trades": trades,
        "portfolio_summary": portfolio_summary,
        "portfolio_weights": portfolio_weights,
        "latest_signal_date": latest_signal_date.strftime("%Y-%m-%d") if pd.notna(latest_signal_date) else None,
        "latest_holdings": latest_holdings,
        "strategy": strategy_context,
        "backtest": backtest_context,
        "data_window": data_window,
    }


def create_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or load_settings()
    app = FastAPI(title="NightFall Alpha", version="0.1.0")
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    price_cache: dict[str, object] = {"mtime": None, "frame": None}

    def cached_prices() -> pd.DataFrame:
        path = artifact_paths(cfg).prices_path
        mtime = path.stat().st_mtime_ns if path.exists() else None
        cached_frame = price_cache.get("frame")
        if isinstance(cached_frame, pd.DataFrame) and price_cache.get("mtime") == mtime:
            return cached_frame
        prices = load_or_create_prices(cfg)
        price_cache["frame"] = prices
        price_cache["mtime"] = path.stat().st_mtime_ns if path.exists() else None
        return prices

    def remember_prices(prices: pd.DataFrame) -> None:
        path = artifact_paths(cfg).prices_path
        price_cache["frame"] = prices
        price_cache["mtime"] = path.stat().st_mtime_ns if path.exists() else None

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        return HTMLResponse(html)

    @app.get("/api/overview")
    def overview() -> dict[str, Any]:
        payload = _load_payload(cfg)
        portfolio_summary = payload["portfolio_summary"]
        candidate_limit = max(1, min(int(payload["strategy"].get("top_n", 25)), 505))
        return {
            "metrics": payload["metrics"],
            "latest_signal_date": payload["latest_signal_date"],
            "latest_holdings": _records(payload["latest_holdings"].head(candidate_limit)),
            "portfolio_summary": _records(portfolio_summary),
            "strategy": payload["strategy"],
            "backtest": payload["backtest"],
            "data_window": payload["data_window"],
        }

    @app.get("/api/equity")
    def equity() -> dict[str, Any]:
        payload = _load_payload(cfg)
        return {"rows": _records(payload["equity"])}

    @app.get("/api/daily")
    def daily() -> dict[str, Any]:
        payload = _load_payload(cfg)
        return {"rows": _records(payload["daily"])}

    @app.get("/api/trades")
    def trades(
        limit: int = 1_000,
        start: str | None = None,
        end: str | None = None,
        symbol: str | None = None,
        pnl: str = "all",
    ) -> dict[str, Any]:
        payload = _load_payload(cfg)
        trades_frame = payload["trades"].copy()
        filtered = _filter_trades_frame(trades_frame, start=start, end=end, symbol=symbol, pnl=pnl)
        frame = filtered.tail(max(1, min(limit, 10_000)))
        summary = _trade_summary(trades_frame, filtered, frame)
        return {"rows": _records(frame), "summary": summary}

    @app.get("/api/trades.csv")
    def trades_csv(
        start: str | None = None,
        end: str | None = None,
        symbol: str | None = None,
        pnl: str = "all",
    ) -> Response:
        payload = _load_payload(cfg)
        frame = _filter_trades_frame(payload["trades"].copy(), start=start, end=end, symbol=symbol, pnl=pnl)
        sort_columns = [column for column in ("exit_date", "signal_date", "symbol", "signal_rank") if column in frame]
        if sort_columns:
            frame = frame.sort_values(sort_columns, kind="mergesort")
        return _csv_response(frame, "nightfall_alpha_trade_blotter.csv")

    @app.get("/api/portfolio-weights")
    def portfolio_weights(portfolio: str | None = None) -> dict[str, Any]:
        payload = _load_payload(cfg)
        frame = payload["portfolio_weights"]
        if portfolio and not frame.empty:
            frame = frame[frame["portfolio"] == portfolio]
        return {"rows": _records(frame)}

    @app.get("/api/universe")
    def universe(refresh_market_caps: bool = False) -> dict[str, Any]:
        frame = load_universe_metadata(cfg, refresh_market_caps=refresh_market_caps)
        cached = frame[frame["in_price_cache"]].copy()
        return {
            "rows": _records(frame),
            "cached_rows": _records(cached),
            "sectors": sorted(frame["sector_code"].dropna().unique().tolist()),
        }

    @app.post("/api/run")
    def rerun(request: SignalBacktestRequest = Body(default_factory=SignalBacktestRequest)) -> dict[str, Any]:
        price_symbols = list(parse_symbols(request.price_symbols)) if request.price_symbols else None
        result = run_research_pipeline(
            cfg,
            force_sample_prices=request.force_sample_prices,
            strategy_overrides=request.model_dump(
                exclude={
                    "force_sample_prices",
                    "price_start",
                    "price_end",
                    "price_symbols",
                    "initial_capital",
                    "fees_bps",
                    "slippage_bps",
                }
            ),
            initial_capital=request.initial_capital,
            fees_bps=request.fees_bps,
            slippage_bps=request.slippage_bps,
            price_start=request.price_start,
            price_end=request.price_end,
            price_symbols=price_symbols,
        )
        return {
            "status": "ok",
            "signals": len(result["signals"]),
            "trades": len(result["backtest"].trades),
            "final_equity": result["metrics"].get("final_equity"),
            "strategy": result["strategy"],
            "data_window": result["data_window"],
        }

    @app.post("/api/data/download")
    def download_data(request: MarketDataRequest) -> dict[str, Any]:
        try:
            symbols = list(parse_symbols(request.tickers)) if request.tickers else None
            result = download_real_market_data(
                cfg,
                symbols=symbols,
                start=request.start,
                end=request.end,
                symbols_limit=request.symbols_limit,
                refresh_universe=symbols is None,
                merge_existing=True,
                source=request.source,
            )
            remember_prices(result.prices)
            payload: dict[str, Any] = {
                "status": "ok",
                "rows": len(result.prices),
                "requested_symbols": result.requested_symbols,
                "returned_symbols": result.returned_symbols,
                "missing_symbols": result.missing_symbols,
            }
            if request.run_backtest:
                strategy_overrides = request.strategy.model_dump(
                    exclude={"initial_capital", "fees_bps", "slippage_bps"}
                ) if request.strategy else None
                pipeline = run_research_pipeline(
                    cfg,
                    strategy_overrides=strategy_overrides,
                    initial_capital=request.strategy.initial_capital if request.strategy else None,
                    fees_bps=request.strategy.fees_bps if request.strategy else None,
                    slippage_bps=request.strategy.slippage_bps if request.strategy else None,
                    price_start=request.start,
                    price_end=request.end,
                    price_symbols=result.returned_symbols,
                )
                payload["final_equity"] = pipeline["metrics"].get("final_equity")
                payload["trades"] = len(pipeline["backtest"].trades)
                payload["data_window"] = pipeline["data_window"]
            return payload
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/portfolio/build")
    def build_portfolio(request: PortfolioBuilderRequest) -> dict[str, Any]:
        try:
            base_prices = cached_prices()
            if request.use_entire_universe:
                symbols = tuple(sorted(base_prices["symbol"].dropna().astype(str).unique().tolist()))
            else:
                symbols = parse_symbols(request.symbols)
            missing = _missing_symbols_from_prices(base_prices, symbols)
            downloaded: list[str] = []
            refresh_history = _should_refresh_portfolio_history(request)
            needs_missing_fill = request.auto_download_missing and bool(missing)
            if symbols and (needs_missing_fill or refresh_history):
                prices, missing, downloaded = ensure_price_history_for_symbols(
                    cfg,
                    symbols,
                    start=request.data_start,
                    source=request.data_source,
                    refresh_existing=refresh_history,
                )
                remember_prices(prices)
            else:
                prices = base_prices
            result = build_custom_portfolio(
                prices,
                PortfolioBuildSpec(
                    symbols=symbols,
                    method=request.method,  # type: ignore[arg-type]
                    return_model=request.return_model,  # type: ignore[arg-type]
                    rebalance_frequency=request.rebalance_frequency,  # type: ignore[arg-type]
                    max_weight=request.max_weight,
                    optimizer_settings=OptimizerSuiteSettings(
                        default_max_weight=request.max_weight,
                        kelly_fraction=request.kelly_fraction,
                        kelly_max_weight=request.kelly_max_weight,
                        mean_variance_risk_aversion=request.mean_variance_risk_aversion,
                        mean_variance_max_weight=request.mean_variance_max_weight,
                        minimum_variance_max_weight=request.minimum_variance_max_weight,
                        inverse_volatility_max_weight=request.inverse_volatility_max_weight,
                        cvar_alpha=request.cvar_alpha,
                        cvar_max_weight=request.cvar_max_weight,
                        black_litterman_tau=request.black_litterman_tau,
                        black_litterman_prior_risk_aversion=request.black_litterman_prior_risk_aversion,
                        black_litterman_risk_aversion=request.black_litterman_risk_aversion,
                        black_litterman_max_weight=request.black_litterman_max_weight,
                    ),
                    risk_free_rate=cfg.portfolio.risk_free_rate,
                    initial_capital=request.initial_capital,
                    fees_bps=request.fees_bps,
                    slippage_bps=request.slippage_bps,
                    lookback_days=_effective_portfolio_lookback(request),
                    allow_symbol_filtering=request.use_entire_universe,
                ),
            )
            effective_lookback = _effective_portfolio_lookback(request)
            return {
                "status": "ok",
                "selected_portfolio": result["selected_portfolio"],
                "return_model": result["return_model"],
                "rebalance_frequency": result.get("rebalance_frequency", request.rebalance_frequency),
                "initial_capital": request.initial_capital,
                "fees_bps": request.fees_bps,
                "slippage_bps": request.slippage_bps,
                "symbols": result["symbols"],
                "excluded_symbols": result.get("excluded_symbols", []),
                "input_symbol_count": result.get("input_symbol_count"),
                "coverage_start_date": result.get("coverage_start_date"),
                "lookback_days": result["lookback_days"],
                "estimation_lookback_days": result.get("estimation_lookback_days"),
                "performance_observations": result.get("performance_observations"),
                "rebalance_count": result.get("rebalance_count", 0),
                "requested_lookback_days": request.lookback_days,
                "effective_lookback_days": effective_lookback,
                "history_mode": "full" if effective_lookback is None else "lookback",
                "data_start": request.data_start,
                "data_source": request.data_source,
                "start_date": result["start_date"],
                "end_date": result["end_date"],
                "optimizer_settings": {
                    "default_max_weight": request.max_weight,
                    "kelly_fraction": request.kelly_fraction,
                    "kelly_max_weight": request.kelly_max_weight,
                    "mean_variance_risk_aversion": request.mean_variance_risk_aversion,
                    "mean_variance_max_weight": request.mean_variance_max_weight,
                    "minimum_variance_max_weight": request.minimum_variance_max_weight,
                    "inverse_volatility_max_weight": request.inverse_volatility_max_weight,
                    "cvar_alpha": request.cvar_alpha,
                    "cvar_max_weight": request.cvar_max_weight,
                    "black_litterman_tau": request.black_litterman_tau,
                    "black_litterman_prior_risk_aversion": request.black_litterman_prior_risk_aversion,
                    "black_litterman_risk_aversion": request.black_litterman_risk_aversion,
                    "black_litterman_max_weight": request.black_litterman_max_weight,
                },
                "missing_symbols": missing,
                "downloaded_symbols": downloaded,
                "summary": _records(result["summary"]),
                "weights": _records(result["weights"]),
                "selected_summary": _records(result["selected_summary"]),
                "selected_weights": _records(result["selected_weights"]),
            }
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return app
