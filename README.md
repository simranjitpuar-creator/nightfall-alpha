# NightFall Alpha

NightFall Alpha is a research and dashboard project for the overnight effect: entering positions near the close and exiting near the next open. The initial scaffold is deliberately dependency-light so it can run in this workspace without extra installs, while leaving clean adapter seams for real market data, broker execution, and heavier optimization engines later.

## What is included

- A synthetic OHLCV data generator for repeatable strategy testing.
- CSV ingestion hooks plus Yahoo Finance downloads for adjusted daily OHLCV data.
- Overnight-effect feature engineering and signal ranking.
- A vectorized backtest with fees, slippage, equity curve, trade blotter, and drawdowns.
- Performance metrics: CAGR, Sharpe, Sortino, max drawdown, Calmar, VaR, CVaR, win rate, profit factor, exposure, turnover, and more.
- Portfolio construction styles: Kelly, mean variance, minimum variance, inverse volatility, CVaR-aware, and Black-Litterman-style posterior returns.
- A custom portfolio builder where you choose tickers or let the app select the best optimizer result.
- A FastAPI dashboard with native browser charts.
- Unit tests for strategy features, risk metrics, and optimizer constraints.

## Quick start

On Windows, double-click `start_nightfall_alpha.bat` from the project folder to start the backend and open the dashboard in your browser. Market data refreshes are controlled from the dashboard so startup stays quick.

From this folder:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m nightfall_alpha.cli sample-data
.\.venv\Scripts\python.exe -m nightfall_alpha.cli backtest
.\.venv\Scripts\python.exe -m nightfall_alpha.cli dashboard --port 8776
```

Then open [http://127.0.0.1:8776](http://127.0.0.1:8776). NightFall Alpha uses `8776` by default so it does not collide with other local dashboards that may already use `8765`.

Startup behavior:

NightFall Alpha no longer downloads market data automatically on launch. Use the Market Data tab when you want to refresh prices, or use the Portfolio Research builder's missing-data controls for targeted fills.

## Real data

Install dependencies, then download real adjusted OHLCV data through `yfinance`:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m pip install yfinance
.\.venv\Scripts\python.exe -m nightfall_alpha.cli real-data --tickers "AAPL,MSFT,NVDA,JPM,XOM,PG,UNH" --start 2018-01-01
```

Omit `--tickers` to fetch the current S&P 500 table and download those symbols. For quick testing, use `--symbols 50`.

The dashboard also has a Market Data panel that can download selected tickers or the S&P 500 universe, then rerun the backtest on demand.

For longer free daily history, use the max-history Yahoo path:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m nightfall_alpha.cli real-data --source yahoo_max --tickers "AAPL,MSFT,JPM" --start 1900-01-01
```

The project also includes a Stooq provider through `pandas-datareader`, but Stooq may challenge automated requests depending on network/session conditions:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m pip install pandas-datareader
.\.venv\Scripts\python.exe -m nightfall_alpha.cli real-data --source stooq --tickers "AAPL,MSFT,JPM" --start 1990-01-01
```

## Portfolio builder

Build a custom portfolio from selected tickers:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m nightfall_alpha.cli portfolio --tickers "AAPL,MSFT,NVDA,AMZN,JPM,XOM,PG,UNH" --method best --return-model overnight --max-weight 0.15
```

Supported methods are `best`, `Kelly 50%`, `Mean Variance`, `Minimum Variance`, `Inverse Volatility`, `CVaR Aware`, and `Black-Litterman`. The dashboard Portfolio Builder exposes the same controls and shows optimizer metrics plus target weights.

In the dashboard, the Portfolio Builder can auto-fill missing tickers. If a ticker is not already present in `data/processed/prices.csv`, the app downloads that ticker through Yahoo Finance, merges it into the local price cache, and then builds the portfolio.

Use `Universe Mode -> Entire Local Universe` to build against every symbol currently present in the local price cache. Use the Universe Selector to choose stocks grouped by SPDR sector code such as `XLK`, `XLF`, and `XLV`; options are sorted by market cap when market-cap metadata is available.

For the builder to use long history, choose `Yahoo Max History`, enable `Refresh history`, and enable `Use all history`. `Data Since` controls what gets downloaded, while `Lookback` controls how much of the downloaded history is used by the optimizer.

Portfolio Research can run static weights or rolling monthly, quarterly, or annual rebalancing. In rebalance mode, `Lookback` is the trailing estimation window used at each rebalance; `Use all history` switches that to expanding prior history.

## Real S&P 500 data path

The project expects a dated universe file at:

```text
data/universe/sp500_constituents.csv
```

Minimum columns:

```csv
symbol,name,sector
AAPL,Apple Inc.,Information Technology
```

For prices, place normalized daily OHLCV data at:

```text
data/processed/prices.csv
```

Required columns:

```csv
date,symbol,open,high,low,close,volume
```

The backtester uses `open_t / close_{t-1} - 1` as the overnight return and forms positions at close `t` for exit at open `t+1`.

## Project layout

```text
src/nightfall_alpha/
  data/          data generation, validation, and pipeline orchestration
  strategy/      overnight-effect features and signal construction
  backtest/      event model, equity curve, trade blotter, metrics
  portfolio/     portfolio optimizers and risk estimators
  dashboard/     FastAPI app and static UI
  trading/       broker/execution interfaces for future paper/live trading
tests/           unittest-based validation suite
config/          default settings
data/            local raw, processed, universe, and report outputs
```

## Notes on trading readiness

This is not live-trading-ready yet. The scaffold intentionally separates research returns from broker execution. Before paper or live trading, add survivorship-bias-free constituents, corporate-action-adjusted prices, exchange calendars, realistic order timing, borrow/short constraints if applicable, broker reconciliation, limits, kill switches, and post-trade audit logs.
