from __future__ import annotations

from pathlib import Path

import pandas as pd
import typer
import uvicorn

from nightfall_alpha.backtest.engine import BacktestConfig
from nightfall_alpha.config import load_settings
from nightfall_alpha.data.pipeline import (
    artifact_paths,
    download_real_market_data,
    load_or_create_prices,
    load_report_csv,
    run_research_pipeline,
)
from nightfall_alpha.portfolio.builder import PortfolioBuildSpec, build_custom_portfolio, parse_symbols

app = typer.Typer(help="NightFall Alpha overnight-effect research toolkit.")


@app.command("sample-data")
def sample_data(
    symbols: int = typer.Option(25, min=1, help="Number of universe symbols to synthesize."),
    start: str = typer.Option("2018-01-01", help="Synthetic sample start date."),
    end: str = typer.Option("2025-12-31", help="Synthetic sample end date."),
    force: bool = typer.Option(False, help="Overwrite data/processed/prices.csv."),
) -> None:
    settings = load_settings()
    prices = load_or_create_prices(settings, force=force, symbols_limit=symbols, start=start, end=end)
    paths = artifact_paths(settings)
    typer.echo(f"Wrote {len(prices):,} OHLCV rows to {paths.prices_parquet_path}")


@app.command("backtest")
def backtest(
    force_sample_prices: bool = typer.Option(False, help="Regenerate synthetic prices before running."),
    symbols: int | None = typer.Option(None, min=1, help="Optional symbol limit for regenerated sample data."),
    data_source: str = typer.Option("existing", help="existing, synthetic, or yfinance."),
    start: str = typer.Option("2018-01-01", help="Start date when downloading/generating data."),
    end: str | None = typer.Option(None, help="Optional end date for real-data downloads."),
    cost_model: str = typer.Option("flat", help="flat or historical era-based costs."),
    capital_capacity: float | None = typer.Option(None, help="Max deployable dollars; excess sits in cash."),
    cash_rate: float = typer.Option(0.0, help="Annualized return on undeployed cash."),
    max_adv_participation: float | None = typer.Option(None, help="Cap each position at this fraction of ADV."),
) -> None:
    result = run_research_pipeline(
        force_sample_prices=force_sample_prices,
        symbols_limit=symbols,
        data_source=data_source,
        start=start,
        end=end,
        cost_model=cost_model,
        capital_capacity=capital_capacity,
        cash_rate=cash_rate,
        max_adv_participation=max_adv_participation,
    )
    paths = result["artifacts"]
    metrics = result["metrics"]
    typer.echo(f"Signals: {len(result['signals']):,}")
    typer.echo(f"Trades: {len(result['backtest'].trades):,}")
    typer.echo(f"Final equity: ${metrics.get('final_equity', 0):,.2f}")
    typer.echo(f"Sharpe: {metrics.get('sharpe')}")
    if metrics.get("survivorship", {}).get("warning"):
        typer.echo(f"Warning: {metrics['survivorship']['warning']}")
    typer.echo(f"Reports written to {Path(paths.metrics_path).parent}")


@app.command("walkforward")
def walkforward(
    train_days: int = typer.Option(756, min=60, help="Training window length in trading days."),
    test_days: int = typer.Option(63, min=5, help="Out-of-sample test window length."),
    step_days: int = typer.Option(63, min=5, help="Roll step between folds."),
    start_date: str | None = typer.Option(None, help="Only keep folds whose test window ends after this date."),
    max_folds: int | None = typer.Option(None, min=1, help="Keep only the most recent N folds."),
    cost_model: str = typer.Option("flat", help="flat or historical era-based costs."),
    selection_metric: str = typer.Option("sharpe", help="sharpe, sortino, calmar, or cagr."),
) -> None:
    from nightfall_alpha.backtest.walkforward import WalkForwardConfig, run_walk_forward

    settings = load_settings()
    prices = load_or_create_prices(settings)
    result = run_walk_forward(
        prices,
        WalkForwardConfig(
            train_days=train_days,
            test_days=test_days,
            step_days=step_days,
            start_date=start_date,
            max_folds=max_folds,
            selection_metric=selection_metric,
        ),
        BacktestConfig(
            initial_capital=settings.backtest.initial_capital,
            fees_bps=settings.backtest.fees_bps,
            slippage_bps=settings.backtest.slippage_bps,
            cost_model=cost_model,
        ),
        risk_free_rate=settings.portfolio.risk_free_rate,
        initial_capital=settings.backtest.initial_capital,
    )
    paths = artifact_paths(settings)
    result.folds.to_csv(paths.walkforward_folds_path, index=False)
    if not result.oos_daily.empty:
        result.oos_daily.to_csv(paths.walkforward_daily_path, index=False)
    typer.echo(f"Folds: {len(result.folds)}")
    typer.echo(f"OOS Sharpe: {result.oos_metrics.get('sharpe')}")
    typer.echo(f"OOS CAGR: {result.oos_metrics.get('cagr')}")
    typer.echo(f"In-sample avg train Sharpe: {result.in_sample_average_sharpe}")
    typer.echo(f"Walk-forward reports written to {paths.walkforward_folds_path.parent}")


@app.command("benchmarks")
def benchmarks(
    keys: str = typer.Option("SP500,SP100,NASDAQ,MSCI_WORLD,UST10Y", help="Comma-separated benchmark keys."),
    refresh: bool = typer.Option(False, help="Re-download benchmark data."),
) -> None:
    from nightfall_alpha.data.benchmarks import benchmark_comparison

    settings = load_settings()
    paths = artifact_paths(settings)
    daily = load_report_csv(paths.daily_path)
    if daily.empty:
        typer.echo("No backtest daily report found. Run a backtest first.")
        raise typer.Exit(code=1)
    daily["exit_date"] = pd.to_datetime(daily["exit_date"])
    strategy_returns = pd.Series(daily["net_return"].to_numpy(dtype=float), index=daily["exit_date"])
    table, _ = benchmark_comparison(
        strategy_returns,
        settings.project.data_dir,
        [key.strip().upper() for key in keys.split(",") if key.strip()],
        refresh=refresh,
        risk_free_rate=settings.portfolio.risk_free_rate,
    )
    if table.empty:
        typer.echo("No benchmark comparison could be produced.")
        raise typer.Exit(code=1)
    typer.echo(table.to_string(index=False))


@app.command("real-data")
def real_data(
    tickers: str | None = typer.Option(None, help="Comma/space-separated tickers. Omit for S&P 500."),
    source: str = typer.Option("yahoo", help="yahoo, yahoo_max, or stooq."),
    start: str = typer.Option("2015-01-01", help="Download start date."),
    end: str | None = typer.Option(None, help="Optional download end date."),
    symbols: int | None = typer.Option(None, min=1, help="Optional symbol limit, useful for quick tests."),
    run_backtest_after: bool = typer.Option(True, help="Run the research pipeline after downloading."),
) -> None:
    settings = load_settings()
    selected = list(parse_symbols(tickers)) if tickers else None
    result = download_real_market_data(
        settings,
        selected,
        start=start,
        end=end,
        symbols_limit=symbols,
        source=source,
        merge_existing=True,
    )
    typer.echo(f"Downloaded {len(result.prices):,} rows for {len(result.returned_symbols):,} symbols.")
    if result.missing_symbols:
        typer.echo(f"Missing symbols: {', '.join(result.missing_symbols[:20])}")
    if run_backtest_after:
        pipeline = run_research_pipeline(settings)
        typer.echo(f"Backtest final equity: ${pipeline['metrics'].get('final_equity', 0):,.2f}")


@app.command("portfolio")
def portfolio(
    tickers: str = typer.Option(..., help="Comma/space-separated tickers to include."),
    method: str = typer.Option("best", help="best, Kelly 50%, Mean Variance, Minimum Variance, Inverse Volatility, CVaR Aware, or Black-Litterman."),
    return_model: str = typer.Option("overnight", help="overnight or close_to_close."),
    max_weight: float = typer.Option(0.12, min=0.0, max=1.0, help="Maximum single-position weight."),
    lookback_days: int = typer.Option(756, min=20, help="Trailing observations to use."),
) -> None:
    settings = load_settings()
    prices = load_or_create_prices(settings)
    result = build_custom_portfolio(
        prices,
        PortfolioBuildSpec(
            symbols=parse_symbols(tickers),
            method=method,  # type: ignore[arg-type]
            return_model=return_model,  # type: ignore[arg-type]
            max_weight=max_weight,
            risk_free_rate=settings.portfolio.risk_free_rate,
            lookback_days=lookback_days,
        ),
    )
    summary = result["selected_summary"]
    weights = result["selected_weights"]
    typer.echo(f"Selected: {result['selected_portfolio']}")
    typer.echo(summary.to_string(index=False))
    typer.echo(weights.to_string(index=False))


@app.command("dashboard")
def dashboard(
    host: str = typer.Option("127.0.0.1", help="Dashboard host."),
    port: int = typer.Option(8776, min=1, max=65535, help="Dashboard port."),
) -> None:
    from nightfall_alpha.dashboard.app import create_app

    uvicorn.run(create_app(), host=host, port=port, log_level="info")


if __name__ == "__main__":
    app()
