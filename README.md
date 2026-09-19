# NightFall Alpha

NightFall Alpha is a research and dashboard project for the overnight effect: entering positions near the close and exiting near the next open. The initial scaffold is deliberately dependency-light so it can run in this workspace without extra installs, while leaving clean adapter seams for real market data, broker execution, and heavier optimization engines later.

## What is included

- A synthetic OHLCV data generator for repeatable strategy testing.
- CSV ingestion hooks plus Yahoo Finance downloads for adjusted daily OHLCV data.
- Overnight-effect feature engineering and signal ranking.
- A vectorized backtest with fees, slippage, equity curve, trade blotter, and drawdowns.
- An era-based historical cost model (toggle between flat bps and decade-appropriate commissions/spreads).
- Capacity modeling: a deployable-capital ceiling with a cash yield on the undeployed remainder, plus per-symbol ADV participation caps.
- Point-in-time index membership support to control survivorship bias (optional `data/universe/sp500_membership.csv`), with an explicit dashboard warning when it is absent.
- Benchmark comparison against S&P 500, S&P 100, Nasdaq Composite, MSCI World (URTH proxy), and approximate 10-year Treasury total returns.
- Walk-forward / out-of-sample evaluation: parameters are re-fit on rolling training windows and scored on the following unseen windows.
- Performance metrics: CAGR, Sharpe, Sortino, max drawdown, Calmar, VaR, CVaR, win rate, profit factor, exposure, turnover, and more.
- Portfolio construction styles: Kelly, mean variance, minimum variance, inverse volatility, CVaR-aware, and Black-Litterman-style posterior returns.
- A custom portfolio builder where you choose tickers or let the app select the best optimizer result.
- A FastAPI dashboard with interactive charts (ECharts), organized as six tabs: Overview, Signal Backtest, Evaluation (Benchmarks + Walk-Forward), Portfolio Research, Trade Blotter, and System (Market Data, Framework Docs, Appearance).
- Unit tests for strategy features, risk metrics, optimizer constraints, cost models, capacity, membership, benchmarks, and walk-forward evaluation.

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

Optional extras: `pip install -e ".[streamlit]"` for the Streamlit UI, `pip install -e ".[broker]"` for the future Interactive Brokers adapter, and `pip install -e ".[dev]"` for the ruff linter.

Then open [http://127.0.0.1:8776](http://127.0.0.1:8776). NightFall Alpha uses `8776` by default so it does not collide with other local dashboards that may already use `8765`.

### Finding your way around

The dashboard opens on the **Overview** tab: a plain-English explanation of the strategy, a live snapshot of the loaded data (price window, universe size, trade count, headline metrics), the five-step workflow with jump buttons into each tab, a first-run quickstart, a glossary of key concepts (overnight return, signal rank, bps, era costs, walk-forward, survivorship bias, capacity, benchmarks), and the caveats to read before trusting any number.

Every control, table column, and chart title has a **? help icon** — hover for a quick explanation, click to pin it. Each note follows the same format: what it is, how it affects the model, and practical details.

Startup behavior:

NightFall Alpha no longer downloads market data automatically on launch. Use the Market Data tab when you want to refresh prices, or use the Portfolio Research builder's missing-data controls for targeted fills.

## Streamlit deployment

The repo includes a Streamlit Cloud entrypoint at:

```text
streamlit_app.py
```

Deploy it from Streamlit Community Cloud with:

```text
Repository: simranjitpuar-creator/nightfall-alpha
Branch: main
Main file path: streamlit_app.py
```

The Streamlit version uses the same NightFall Alpha Python research engine and recreates the local dashboard's tabs, dark fintech theme, metrics, portfolio builder, benchmark comparison, walk-forward evaluation, charts, trade blotter, CSV downloads, and framework notes. Streamlit Cloud will not include ignored local caches such as `data/processed/prices.parquet` or `data/reports/*`; use the Market Data page in the deployed app to refresh real Yahoo or Stooq data into that runtime.

To run the Streamlit version locally:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run streamlit_app.py
```

## Cost models, capacity, and survivorship

The backtest supports two cost models, selectable in the dashboards, the CLI, and `config/settings.yml`:

- `flat`: the configured `fees_bps` + `slippage_bps` apply to every date.
- `historical`: an era-based table (`src/nightfall_alpha/backtest/costs.py`) charges realistic costs for the period — fixed commissions and wide fractional spreads before 1975, falling through decimalization (2001) and Reg NMS to near-modern costs after 2015. A 64-year backtest run at flat 1.5 bps/side materially overstates historical performance; the historical toggle shows the difference.

Capacity controls keep the equity curve realistic:

- `capital_capacity` caps deployable capital each night; excess equity sits in cash earning `cash_rate`. Without a cap the compounding curve is mathematically unbounded (and meaningless beyond market scale).
- `max_adv_participation` caps each position's notional at a fraction of the symbol's 20-day median dollar volume, so the strategy cannot "trade" more than a realistic share of liquidity.

Survivorship bias: by default the universe is today's S&P 500 constituents applied to historical prices, which overstates returns (delisted names are missing and members are treated as always included). To control this, provide point-in-time membership windows at `data/universe/sp500_membership.csv`:

```csv
symbol,start_date,end_date
AAPL,1982-11-30,
GE,1907-11-07,2018-06-26
```

When the file exists, the pipeline masks prices to each symbol's actual membership window. When it does not, both dashboards display an explicit survivorship-bias warning banner.

## Benchmarks and walk-forward

The Benchmarks dashboard tab (or `nightfall-alpha benchmarks`) compares the strategy against S&P 500, S&P 100, Nasdaq Composite, MSCI World (URTH ETF proxy), and an approximate 10-year Treasury total return derived from the ^TNX yield index. It reports CAGR, volatility, Sharpe, max drawdown for the benchmark plus correlation, beta, annualized alpha, tracking error, information ratio, and up/down capture versus the strategy, over common trading dates.

The Walk-Forward tab (or `nightfall-alpha walkforward`) replaces the in-sample parameter choice with rolling out-of-sample evaluation: for each fold, the parameter grid (lookback, top-N, min-signal) is scored on a training window, frozen, and then measured on the following unseen test window. The stitched OOS equity curve and the in-sample vs out-of-sample Sharpe decay are the honest headline numbers for the strategy.

```powershell
.\.venv\Scripts\python.exe -m nightfall_alpha.cli walkforward --start-date 2015-01-01 --cost-model historical
.\.venv\Scripts\python.exe -m nightfall_alpha.cli backtest --cost-model historical --capital-capacity 250000000 --max-adv-participation 0.05
```

## Real data

Download real adjusted OHLCV data through `yfinance` (a core dependency, no extra install needed):

```powershell
$env:PYTHONPATH = "src"
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

### Tiingo (free API key)

Tiingo offers an official free end-of-day API: 500 requests/day, full history per symbol, adjusted prices. Sign up at https://www.tiingo.com, copy the key from Account → API, then set it in `.env` or the environment:

```powershell
TIINGO_API_KEY=your_key_here
.\.venv\Scripts\python.exe -m nightfall_alpha.cli real-data --source tiingo --tickers "AAPL,MSFT,JPM" --start 2015-01-01
```

### Incremental refreshes

Daily top-ups no longer need a full history re-download. Pass `--incremental` (CLI) or enable "Incremental (new bars only)" (dashboards) to fetch only bars after each symbol's last cached date, with a 10-day overlap that is deduplicated on merge:

```powershell
.\.venv\Scripts\python.exe -m nightfall_alpha.cli real-data --source tiingo --incremental
```

## Portfolio builder

Build a custom portfolio from selected tickers:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m nightfall_alpha.cli portfolio --tickers "AAPL,MSFT,NVDA,AMZN,JPM,XOM,PG,UNH" --method best --return-model overnight --max-weight 0.15
```

Supported methods are `best`, `Kelly 50%`, `Mean Variance`, `Minimum Variance`, `Inverse Volatility`, `CVaR Aware`, and `Black-Litterman`. The dashboard Portfolio Builder exposes the same controls and shows optimizer metrics plus target weights.

In the dashboard, the Portfolio Builder can auto-fill missing tickers. If a ticker is not already present in the local price cache (`data/processed/prices.parquet`), the app downloads that ticker through Yahoo Finance, merges it into the cache, and then builds the portfolio.

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

For prices, the primary local cache is the parquet file at:

```text
data/processed/prices.parquet
```

A legacy CSV at `data/processed/prices.csv` is still read if present and is automatically migrated to parquet on first load. Required columns:

```csv
date,symbol,open,high,low,close,volume
```

The backtester uses `open_t / close_{t-1} - 1` as the overnight return and forms positions at close `t` for exit at open `t+1`.

## Project layout

```text
src/nightfall_alpha/
  data/          data generation, validation, providers, membership, benchmarks, pipeline orchestration
  strategy/      overnight-effect features and signal construction
  backtest/      event model, era cost schedules, equity curve, trade blotter, metrics, walk-forward
  portfolio/     portfolio optimizers and risk estimators
  dashboard/     FastAPI app and static UI
  trading/       broker/execution interfaces for future paper/live trading
tests/           unittest-based validation suite
config/          default settings
data/            local raw, processed (parquet price cache), universe, and report outputs
```

## Notes on trading readiness

This is not live-trading-ready yet. The scaffold intentionally separates research returns from broker execution. The era-based cost model, capacity caps, point-in-time membership support, and walk-forward evaluation address the largest research-bias risks, but before paper or live trading you still need true survivorship-bias-free constituent data (the membership file is only as good as its source), corporate-action-adjusted prices, exchange calendars, realistic order timing, borrow/short constraints if applicable, broker reconciliation, limits, kill switches, and post-trade audit logs.
