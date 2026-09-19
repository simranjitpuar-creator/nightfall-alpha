const state = {
  overview: null,
  equity: [],
  daily: [],
  trades: [],
  tradeSummary: null,
  builder: null,
  universe: [],
  eraStudyLoaded: false,
  curves: {
    range: "full",
    hoverIndex: null,
  },
};

const metricSpecs = [
  ["Initial Equity", "initial_capital", "money"],
  ["Ending Equity", "final_equity", "money"],
  ["Total Return", "total_return", "pct", "signed"],
  ["CAGR", "cagr", "pct", "signed"],
  ["Annual Vol", "annualized_volatility", "pct"],
  ["Sharpe", "sharpe", "number"],
  ["Sortino", "sortino", "number"],
  ["Calmar", "calmar", "number"],
  ["1Y Roll Sharpe", "rolling_sharpe_1y", "number"],
  ["3Y Roll Sharpe", "rolling_sharpe_3y", "number"],
  ["5Y Roll Sharpe", "rolling_sharpe_5y", "number"],
  ["1Y Roll Sortino", "rolling_sortino_1y", "number"],
  ["3Y Roll Sortino", "rolling_sortino_3y", "number"],
  ["5Y Roll Sortino", "rolling_sortino_5y", "number"],
  ["1Y Roll Calmar", "rolling_calmar_1y", "number"],
  ["3Y Roll Calmar", "rolling_calmar_3y", "number"],
  ["5Y Roll Calmar", "rolling_calmar_5y", "number"],
  ["Max DD", "max_drawdown", "pct", "signed"],
  ["Win Rate", "win_rate", "pct"],
  ["Profit Factor", "profit_factor", "number"],
  ["VaR 95", "var_95", "pct", "signed"],
  ["CVaR 95", "cvar_95", "pct", "signed"],
  ["Cost Drag", "total_cost_return", "pct"],
  ["Avg Exposure", "exposure", "pct"],
  ["Avg Turnover", "average_round_trip_turnover", "pct"],
];

const portfolioMetricSpecs = [
  ["Start", "start_date", "date"],
  ["End", "end_date", "date"],
  ["Years", "elapsed_years", "years"],
  ["Obs", "observations", "integer"],
  ["Initial Equity", "initial_capital", "money"],
  ["Ending Equity", "final_equity", "money"],
  ["Period Return", "total_return", "pct", "signed"],
  ["CAGR", "cagr", "pct", "signed"],
  ["Ann Return", "annualized_return", "pct", "signed"],
  ["Annual Vol", "annualized_volatility", "pct"],
  ["Sharpe", "sharpe", "number"],
  ["Sortino", "sortino", "number"],
  ["Calmar", "calmar", "number"],
  ["1Y Sharpe", "rolling_sharpe_1y", "number"],
  ["3Y Sharpe", "rolling_sharpe_3y", "number"],
  ["5Y Sharpe", "rolling_sharpe_5y", "number"],
  ["1Y Sortino", "rolling_sortino_1y", "number"],
  ["3Y Sortino", "rolling_sortino_3y", "number"],
  ["5Y Sortino", "rolling_sortino_5y", "number"],
  ["1Y Calmar", "rolling_calmar_1y", "number"],
  ["3Y Calmar", "rolling_calmar_3y", "number"],
  ["5Y Calmar", "rolling_calmar_5y", "number"],
  ["Max DD", "max_drawdown", "pct", "signed"],
  ["Win Rate", "win_rate", "pct"],
  ["Profit Factor", "profit_factor", "number"],
  ["VaR 95", "var_95", "pct", "signed"],
  ["CVaR 95", "cvar_95", "pct", "signed"],
  ["Cost Drag", "total_cost_return", "pct"],
  ["Invested", "weight_sum", "pct"],
  ["Cash", "cash_weight", "pct"],
  ["Cap", "max_weight_limit", "pct"],
  ["Max Weight", "max_weight", "pct"],
  ["Rebalances", "rebalance_count", "integer"],
  ["Avg Turnover", "average_turnover", "pct"],
];

const tradeMetricSpecs = [
  ["Source Trades", "source_total_trades", "integer"],
  ["Filtered Trades", "filtered_trades", "integer"],
  ["Loaded Rows", "returned_trades", "integer"],
  ["Symbols", "filtered_symbols", "integer"],
  ["Source Start", "source_start_date", "date"],
  ["Source End", "source_end_date", "date"],
  ["Latest Exit", "latest_exit_date", "date"],
  ["Latest Book Trades", "latest_trade_count", "integer"],
  ["Win Rate", "win_rate", "pct"],
  ["Total Net PnL", "total_net_pnl", "moneyFine", "signed"],
  ["Avg Trade PnL", "average_trade_pnl", "moneyFine", "signed"],
  ["Best Trade", "best_trade_pnl", "moneyFine", "signed"],
  ["Worst Trade", "worst_trade_pnl", "moneyFine", "signed"],
  ["Total Costs", "total_cost", "moneyFine", "signed"],
  ["Avg Weight", "average_weight", "pct"],
];

function cssVar(name, fallback) {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

function chartColors() {
  const rgb = cssVar("--accent-rgb", "99, 102, 241");
  return {
    text: cssVar("--text", "#e9eef8"),
    muted: cssVar("--muted", "#8a94ac"),
    grid: cssVar("--grid", "rgba(255,255,255,0.07)"),
    gridStrong: cssVar("--grid-strong", "rgba(255,255,255,0.18)"),
    chartBg: cssVar("--chart-bg", "transparent"),
    accent: cssVar("--accent", "#6366f1"),
    accentRgb: rgb,
    accentSoftTop: `rgba(${rgb}, 0.28)`,
    accentSoftBottom: `rgba(${rgb}, 0.02)`,
    loss: cssVar("--loss", "#fb7185"),
    lossSoft: "rgba(251, 113, 133, 0.16)",
  };
}

const CHART_FONT = "Inter, 'Segoe UI', Arial";
const CHART_MONO = "'JetBrains Mono', ui-monospace, monospace";

function formatNumber(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  return Number(value).toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

function formatMoney(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  return Number(value).toLocaleString(undefined, {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  });
}

function formatMoneyFine(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  return Number(value).toLocaleString(undefined, {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
    minimumFractionDigits: 2,
  });
}

function formatPct(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  return `${(Number(value) * 100).toFixed(digits)}%`;
}

function formatCompactMoney(value) {
  const number = Number(value);
  if (!Number.isFinite(number) || number <= 0) return "";
  if (number >= 1e15) return `$${number.toExponential(2)}`;
  if (number >= 1e12) return `$${(number / 1e12).toFixed(1)}T`;
  if (number >= 1e9) return `$${(number / 1e9).toFixed(1)}B`;
  if (number >= 1e6) return `$${(number / 1e6).toFixed(0)}M`;
  return formatMoney(number);
}

function formatAxisMoney(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  const sign = number < 0 ? "-" : "";
  const absolute = Math.abs(number);
  if (absolute >= 1e12) return `${sign}$${(absolute / 1e12).toFixed(1)}T`;
  if (absolute >= 1e9) return `${sign}$${(absolute / 1e9).toFixed(1)}B`;
  if (absolute >= 1e6) return `${sign}$${(absolute / 1e6).toFixed(1)}M`;
  if (absolute >= 1e3) return `${sign}$${(absolute / 1e3).toFixed(0)}K`;
  return `${sign}$${absolute.toFixed(0)}`;
}

function formatShortDate(value) {
  if (!value) return "";
  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleDateString(undefined, { month: "short", year: "2-digit" });
}

function formatByType(value, type) {
  if (type === "date") return value || "-";
  if (type === "integer") {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
    return Number(value).toLocaleString(undefined, { maximumFractionDigits: 0 });
  }
  if (type === "years") {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
    return Number(value).toLocaleString(undefined, { maximumFractionDigits: 2, minimumFractionDigits: 2 });
  }
  if (type === "money") return formatMoney(value);
  if (type === "moneyFine") return formatMoneyFine(value);
  if (type === "pct") return formatPct(value);
  return formatNumber(value);
}

function numberInputValue(id, fallback) {
  const value = document.getElementById(id)?.value;
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function optionalNumberInputValue(id) {
  const value = document.getElementById(id)?.value;
  if (value === null || value === undefined || String(value).trim() === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function builderUsesFullHistory() {
  const useAllHistory = document.getElementById("useAllHistory")?.checked;
  return Boolean(useAllHistory);
}

function renderPortfolioMetricCells(row) {
  return portfolioMetricSpecs.map(([, key, type, tone]) => {
    const valueClass = tone === "signed" ? signedClass(row[key]) : "";
    return `<td class="${valueClass}">${formatByType(row[key], type)}</td>`;
  }).join("");
}

function latestWeightRows(rows) {
  const datedRows = rows.filter((row) => row.rebalance_date);
  if (!datedRows.length) return rows;
  const latestDate = datedRows.reduce((latest, row) => String(row.rebalance_date) > latest ? String(row.rebalance_date) : latest, "");
  return rows.filter((row) => String(row.rebalance_date || "") === latestDate);
}

function signedClass(value) {
  const number = Number(value);
  if (!Number.isFinite(number) || number === 0) return "";
  return number > 0 ? "gain" : "loss";
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch {
      detail = `${response.status} ${response.statusText}`;
    }
    throw new Error(detail);
  }
  return response.json();
}

function toast(message) {
  const node = document.getElementById("toast");
  node.textContent = message;
  node.classList.add("show");
  window.setTimeout(() => node.classList.remove("show"), 2400);
}

function csvEscape(value) {
  if (value === null || value === undefined) return "";
  const text = String(value);
  return /[",\n\r]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

function rowsToCsv(rows, columns) {
  const header = columns.map((column) => csvEscape(column.label)).join(",");
  const body = rows.map((row) => (
    columns.map((column) => csvEscape(
      typeof column.value === "function" ? column.value(row) : row[column.value]
    )).join(",")
  ));
  return [header, ...body].join("\n");
}

function downloadTextFile(filename, content, mimeType = "text/csv") {
  const blob = new Blob([content], { type: `${mimeType};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function openDownloadUrl(url) {
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}

const HELP_TEXT = {
  dataSource: `Description: Selects the market data provider used to refresh the local daily OHLCV price cache.
Model impact: This controls the raw price history available to the signal backtest and portfolio builder. Longer histories can change rolling signals, risk estimates, covariance matrices, VaR, CVaR, and optimizer outputs.
Details: Yahoo Finance is usually fastest for common US equities. Yahoo Max asks Yahoo for the longest available history. Stooq can provide long adjusted daily history and the app handles US ticker formatting for it.`,
  dataTickers: `Description: Optional comma-separated ticker list for the Market Data refresh.
Model impact: When filled, the download and optional signal backtest are restricted to these symbols. When blank, the app uses the S&P 500 universe metadata.
Details: Use standard tickers like AAPL, MSFT, NVDA. A narrow list runs faster and is useful for debugging; a broad list gives more realistic universe-level strategy behavior.`,
  dataStart: `Description: First date requested for the Market Data download.
Model impact: Earlier starts give the backtest and optimizer more historical observations, which can stabilize rolling Sharpe, covariance, drawdown, VaR, and CVaR estimates.
Details: The actual first date can still be later if the provider or ticker does not have older history. Yahoo Max intentionally pushes this far back.`,
  dataEnd: `Description: Last date requested for the Market Data download.
Model impact: This caps the data window used by the optional run-after-download signal backtest, so equity and drawdown curves should line up with this data window.
Details: Leave blank to download through the provider's latest available daily bar.`,
  dataLimit: `Description: Maximum number of S&P 500 symbols to download when the Tickers field is blank.
Model impact: Smaller limits make refreshes faster but produce a partial universe. Larger limits are closer to an index-wide test but take longer and may hit provider limits.
Details: This is ignored when you type specific tickers.`,
  runAfterDownload: `Description: Runs the signal backtest immediately after the Market Data refresh finishes.
Model impact: When enabled, the new price window and returned symbols are passed into the signal engine so the curves, metrics, candidates, and trade blotter update from the fresh cache.
Details: Turn it off if you only want to update raw prices before testing a separate backtest configuration.`,
  signalInitialEquity: `Description: Starting dollar value for the Signal Backtest before any overnight trades are applied.
Model impact: This scales the equity curve, ending equity, trade notionals, gross PnL, net PnL, and dollar-based metrics. Percentage returns, Sharpe, Sortino, drawdown percentage, win rate, VaR percentage, and CVaR percentage should not change just because the starting equity changes.
Details: Enter the account size or hypothetical capital base you want the backtest to compound from. For example, 100000 means the first trade book starts from $100,000.`,
  signalFeesBps: `Description: Explicit trading fee assumption for the Signal Backtest, measured in basis points per side.
Model impact: Higher fees reduce daily net return, ending equity, Sharpe, Sortino, Calmar, trade net PnL, and the trade blotter's net results.
Details: The signal model applies fees on both entry and exit: 2 * gross exposure * (fees plus slippage) / 10000.`,
  signalSlippageBps: `Description: Execution slippage assumption for the Signal Backtest, measured in basis points per side.
Model impact: Higher slippage increases cost drag and lowers net strategy performance without changing raw signal ranks.
Details: Use this to stress test overnight fills around the close/open where spreads and auction behavior can matter.`,
  signalLookbackDays: `Description: Number of recent trading days used to calculate each stock's overnight signal score.
Model impact: The app ranks candidates primarily by rolling overnight Sharpe over this window. Short windows react faster but are noisier; long windows are smoother but slower to adapt.
Details: This is separate from the chart zoom window and separate from the portfolio builder lookback.`,
  signalMinHistory: `Description: Minimum number of valid overnight observations a stock must have before it can enter the backtest.
Model impact: Higher values reduce sparse or newly listed names and make signal estimates more reliable, but they can shrink the eligible universe early in the sample.
Details: This should usually be lower than or equal to the signal lookback.`,
  signalTopN: `Description: Number of highest-ranked overnight candidates selected each signal date.
Model impact: Lower values create a more concentrated book; higher values diversify across more names and usually reduce single-name noise.
Details: The Current Overnight Candidates table is capped by this value.`,
  signalMaxWeight: `Description: Maximum target allocation allowed for any single signal candidate.
Model impact: This caps concentration in the backtest portfolio. Lower caps force more diversification; higher caps let the strongest ranks dominate more of the book.
Details: Enter as a decimal, so 0.07 means 7 percent.`,
  signalMinSignal: `Description: Minimum signal threshold required for a stock to be selected.
Model impact: Raising this filter makes the strategy more selective and can leave cash undeployed when too few names qualify. Lowering it allows weaker candidates into the book.
Details: Signal values are rolling overnight Sharpe-like scores, so the scale depends on the chosen lookback and available history.`,
  signalCapitalCapacity: `Description: Maximum dollars the strategy may deploy each day, regardless of how large the account has grown.
Model impact: When set above 0, daily deployed capital is capped at this value and the excess sits in cash earning the Cash Rate. This flattens the equity curve's dollar growth once the account outgrows the cap, while percentage metrics reflect only the deployable book.
Details: Use it to answer "how big can this strategy actually get?" — a real overnight book cannot scale forever. Enter 0 to disable the cap.`,
  signalCashRate: `Description: Annualized interest rate earned on undeployed cash, entered as a percent.
Model impact: When the book does not use 100 percent of equity (Top N x Max Weight below 1, or a Capital Capacity cap), the idle portion earns this rate divided by 252 each day, slightly raising net returns and Sharpe.
Details: Enter 4 for roughly a 4 percent T-bill-style yield. 0 treats cash as earning nothing, the conservative default.`,
  signalAdvParticipation: `Description: Maximum share of each stock's average daily dollar volume (ADV) the strategy may trade, entered as a percent.
Model impact: Per-name weights are capped so the traded notional never exceeds this fraction of that stock's ADV. Thinly traded names get scaled down first, which reduces exposure exactly where real fills would be hardest.
Details: 10 means no more than 10 percent of a name's daily dollar volume. 0 disables the liquidity check. Combine with Capital Capacity to find the realistic size limit of the strategy.`,
  signalPriceStart: `Description: First price date used by the Signal Backtest.
Model impact: This controls the beginning of the backtest data window for equity, drawdown, metrics, candidates, and trades.
Details: It is normally synced from the Market Data tab after a download, but you can override it here for research runs. The date is a filter on the local cache, not a data source: if you pick a date earlier than the cache's first bar (currently 1962-01-02, Yahoo's adjusted-history floor for most tickers), the run starts at the first available bar and the summary line says so. To test earlier periods, download older history first — Stooq can reach further back for some names.`,
  signalPriceEnd: `Description: Last price date used by the Signal Backtest.
Model impact: This controls the ending data window for the signal backtest and prevents the curves from using data outside the selected research range.
Details: Leave blank to use the latest cached date available for the selected symbols.`,
  signalPriceTickers: `Description: Optional ticker subset for the Signal Backtest.
Model impact: When filled, the signal engine only uses these cached symbols. When blank, it uses all symbols currently available in the local price cache after the date filters.
Details: This is useful for testing a custom mini-universe without changing the Market Data cache.`,
  benchmarkRefresh: `Description: Chooses whether the benchmark comparison uses the cached benchmark files or re-downloads them from Yahoo.
Model impact: Re-downloading picks up newer benchmark history but takes longer; the numbers only change where the underlying benchmark data changed.
Details: Leave on Use cache for day-to-day comparisons; re-download after long gaps or if a benchmark looks stale.`,
  wfTrainDays: `Description: Number of trading days in each walk-forward training window.
Model impact: Longer windows estimate parameters more stably but adapt more slowly to regime changes; shorter windows adapt faster but can overfit noise.
Details: 756 days is roughly three trading years. Parameters are re-fit inside every fold.`,
  wfTestDays: `Description: Number of trading days in each out-of-sample test window.
Model impact: Longer tests give more reliable per-fold OOS statistics but fewer total folds; shorter tests give more folds with noisier numbers.
Details: 63 days is roughly one trading quarter.`,
  wfStepDays: `Description: How far the window rolls forward between folds.
Model impact: Steps smaller than Test Days create overlapping test windows (more folds, correlated results); steps equal to Test Days give clean non-overlapping evaluation.
Details: Keep Step equal to Test unless you deliberately want overlapping folds.`,
  wfMaxFolds: `Description: Caps how many walk-forward folds actually run. 0 means all possible folds.
Model impact: Fewer folds finish much faster — each fold re-fits parameters on a full training window.
Details: The default of 8 gives a first answer in under a minute; raise it once the setup looks right.`,
  wfStartDate: `Description: Earliest allowed end date for a test window.
Model impact: Skips folds whose test period ends before this date, focusing evaluation on more recent, more relevant regimes.
Details: Useful because early-history data is thinner and era costs make old results less comparable.`,
  wfMetric: `Description: The metric used to pick the best parameters on each training window.
Model impact: Sharpe favors smooth risk-adjusted returns; Sortino penalizes downside more; Calmar focuses on drawdown; CAGR chases raw growth.
Details: The chosen metric is maximized in-sample, then the frozen parameters are scored out-of-sample.`,
  wfCostModel: `Description: Cost model used inside walk-forward evaluation.
Model impact: Historical charges era-realistic bps (much higher in early decades), which can change which parameters win; Flat charges the same bps everywhere.
Details: Use historical for honest long-window studies, flat when comparing against the flat-cost backtest.`,
  tradeSymbolFilter: `Description: Restricts the blotter to symbols containing this text.
Model impact: Display-only filter — the underlying trade history is unchanged.
Details: Case-insensitive substring match, so AA matches AAPL and AAL. Clear it to see all symbols.`,
  tradeStartFilter: `Description: First entry date shown in the blotter.
Model impact: Display-only filter — no recomputation.
Details: Combine with the PnL filter to audit losing trades in a specific era, like the 2008 crisis.`,
  tradeEndFilter: `Description: Last entry date shown in the blotter.
Model impact: Display-only filter — no recomputation.
Details: Leave blank to include the most recent trades.`,
  tradePnlFilter: `Description: Shows all trades, only winners (net PnL above zero), or only losers.
Model impact: Display-only filter — the summary cards still show totals for the filtered set.
Details: Losers view is the fastest way to spot cost drag or systematically bad symbols.`,
  tradeLimitFilter: `Description: Maximum number of table rows returned, taken from the most recent matching trades.
Model impact: Display-only — the summary counts still reflect every matching trade.
Details: The full filtered set (beyond this cap) is always available via Download CSV.`,
  optimizeCandidatesButton: `Description: Sends the current overnight candidate list straight into the Portfolio Builder and runs the optimizer suite on those names.
Model impact: The builder switches to Selected Stocks universe mode and the Overnight return model, fills the ticker field with tonight's book, and builds immediately — so the optimizer weights are estimated on the same names the signal ranks produced.
Details: This is the bridge between the two research tracks: the signal picks the names, the optimizer sizes them. Compare the optimizer weights against the signal book's rank-based weights, and check which optimizer the app marks Best Sharpe.`,
  universeMode: `Description: Chooses whether the portfolio builder uses only typed/selected tickers or the entire locally cached universe.
Model impact: Selected Stocks gives controlled custom portfolios. Entire Local Universe lets the optimizer search across all cached symbols, which can materially change weights and risk metrics.
Details: Entire universe runs can take longer and depend heavily on data availability.`,
  builderDataSource: `Description: Data source used when the portfolio builder needs to fill missing or refreshed price history.
Model impact: The chosen source affects available history, return estimates, covariance estimates, and optimizer results.
Details: This does not refresh data by itself. It only applies when Auto-fill Missing needs a symbol that is not cached, or when Refresh History is checked. Yahoo Max and Stooq are better when you explicitly want longer history.`,
  portfolioTickers: `Description: Comma-separated symbols for custom portfolio construction.
Model impact: These symbols define the investable universe when Universe Mode is set to Selected Stocks. The optimizer can only allocate to names listed here.
Details: The Add Selected button appends names from the sector-organized universe selector.`,
  universeSelect: `Description: Multi-select list of available stocks grouped by sector ETF code and sorted by market cap.
Model impact: Selected names can be added to the custom ticker list, shaping the universe that the optimizer can allocate across.
Details: Entries marked cached already have price history in the local cache; uncached names may need auto-fill.`,
  returnModel: `Description: Return series used by the portfolio optimizer.
Model impact: Overnight focuses on close-to-next-open behavior tied to the strategy idea. Close to Close uses ordinary daily returns and can produce very different expected returns, risk, and correlations.
Details: Use Overnight when the portfolio is meant to express the overnight effect.`,
  builderInitialEquity: `Description: Starting dollar value used to scale Portfolio Research performance metrics.
Model impact: This scales Initial Equity, Ending Equity, and dollar-based equity metrics for each optimized portfolio. It does not change percentage returns, Sharpe, Sortino, Calmar, VaR percentage, CVaR percentage, or optimizer weights.
Details: Use the same capital base as the Signal Backtest if you want dollar results to compare cleanly across tabs.`,
  builderFeesBps: `Description: Explicit trading fee assumption for Portfolio Research, measured in basis points per side.
Model impact: Higher fees reduce net portfolio returns through allocation, rebalance, and daily drift-rebalancing turnover.
Details: Fees are uniform per trade — every stock pays the same fee rate. Slippage, by contrast, is scaled per stock: volatile names pay more, calm names less.`,
  builderSlippageBps: `Description: Execution slippage assumption for Portfolio Research, measured in basis points per side.
Model impact: Higher slippage lowers net optimizer performance, especially for high-turnover or high-volatility books.
Details: This is the average rate: each stock's actual slippage is scaled by its relative daily volatility (0.25x to 4x the cross-sectional mean), so jumpy names cost more to trade than calm ones. Charged on the initial allocation, rebalance turnover, and daily drift rebalancing.`,
  maxWeight: `Description: Default maximum weight any one stock can receive in the portfolio optimizer suite.
Model impact: This is the cap used by every optimizer unless that optimizer has its own cap override below. Lower caps reduce concentration and can leave more capital in Cash when the usable universe is small.
Details: Enter as a decimal, so 0.01 means 1 percent. The Cap, Invested, Cash, and Max Weight columns show how the constraint was applied.`,
  rebalanceFrequency: `Description: Controls whether Portfolio Research uses one static weight set or recalculates weights through time.
Model impact: Static Weights optimizes once and applies one target portfolio over the displayed window. Monthly, Quarterly, and Annually recalculate each optimizer at the first available trading row of each period, using only prior return history, then hold those weights until the next rebalance.
Details: When Use All History is off, Lookback is the trailing estimation window used at each rebalance. When Use All History is on, the rebalance engine uses expanding prior history. This is the true rebalance frequency control.`,
  optimizerSettingsTitle: `Description: Method-specific controls for the Portfolio Research optimizer suite.
Model impact: One Build Portfolio click runs every optimizer with these settings. Blank cap overrides use Default Max Weight, while filled cap overrides let a single optimizer be more or less concentrated than the rest.
Details: These settings affect the Current Builder Optimizer Suite only. The Saved Signal Universe Suite comes from the latest signal/data pipeline run.`,
  kellyFraction: `Description: Fraction of the raw Kelly allocation to deploy.
Model impact: Lower values make Kelly more conservative and can leave more cash undeployed. Higher values increase Kelly exposure up to the cap.
Details: 0.50 is half Kelly, 1.00 is full Kelly, and 0.00 forces Kelly to hold cash.`,
  kellyMaxWeight: `Description: Optional max-weight cap used only by the Kelly optimizer.
Model impact: If filled, this overrides Default Max Weight for Kelly and directly limits each Kelly position.
Details: Leave blank to use Default Max Weight. Enter 0.01 for a 1 percent cap.`,
  meanVarianceRiskAversion: `Description: Controls how much the Mean Variance optimizer dislikes variance relative to expected return.
Model impact: The optimizer balances expected return against covariance risk. Higher values make risk more expensive, so weights usually become more diversified, lower-volatility, and less driven by small expected-return differences. Lower values make the optimizer more return-seeking and can concentrate into names with higher estimated returns.
Details: The app does not estimate this value automatically; you enter it. Internally it uses daily winsorized mean returns and the daily covariance matrix, then approximately solves: maximize mu' * w - 0.5 * lambda * w' * Sigma * w, with long-only weights and max-weight caps. The default 8 is intentionally conservative because short-horizon overnight expected returns are noisy.`,
  meanVarianceMaxWeight: `Description: Optional max-weight cap used only by Mean Variance.
Model impact: If filled, this overrides Default Max Weight for Mean Variance and controls concentration in that row.
Details: Leave blank to use the default cap shared by the suite.`,
  minimumVarianceMaxWeight: `Description: Optional max-weight cap used only by Minimum Variance.
Model impact: This optimizer minimizes volatility, so the cap controls whether it can concentrate in the lowest-risk names or must diversify more broadly.
Details: Leave blank to use Default Max Weight.`,
  inverseVolatilityMaxWeight: `Description: Optional max-weight cap used only by Inverse Volatility.
Model impact: Inverse Volatility favors lower-volatility stocks; this cap limits how much any one low-volatility name can receive.
Details: Leave blank to use Default Max Weight.`,
  cvarAlpha: `Description: Confidence level for the CVaR Aware optimizer.
Model impact: Higher values focus on a narrower, more extreme loss tail. Lower values consider a broader tail sample and can produce smoother allocations.
Details: 0.95 means the optimizer pays attention to the worst 5 percent of historical portfolio outcomes.`,
  cvarMaxWeight: `Description: Optional max-weight cap used only by CVaR Aware.
Model impact: If filled, this overrides Default Max Weight for the tail-risk optimizer.
Details: Leave blank to use Default Max Weight.`,
  blackLittermanTau: `Description: Uncertainty scale applied to the Black-Litterman prior.
Model impact: Lower tau makes the prior more stable. Higher tau lets observed return/covariance information shift the posterior more.
Details: 0.05 is a common conservative default.`,
  blackLittermanPriorRiskAversion: `Description: Controls the risk penalty used to infer Black-Litterman's equilibrium prior returns from the market-weighted portfolio.
Model impact: Higher values produce larger implied prior returns for assets that carry more covariance risk, meaning the prior says investors require more compensation to hold that risk. Lower values create a milder prior that is less forceful before the posterior is formed.
Details: The app does not estimate this value automatically; you enter it. Internally the prior is calculated as pi = delta * Sigma * market_weights, where delta is Prior Risk Aversion, Sigma is the daily covariance matrix, and market_weights are equal weights across the selected universe. This shapes the return forecast before allocation.`,
  blackLittermanRiskAversion: `Description: Controls how much risk is penalized in the final Black-Litterman allocation after posterior returns are estimated.
Model impact: Higher values make the final Black-Litterman portfolio more conservative, diversified, and volatility-aware. Lower values let the posterior return estimates drive larger active bets, subject to the max-weight cap.
Details: The app does not estimate this value automatically; you enter it. After the Black-Litterman prior/posterior return vector is created, the final allocation uses the same mean-variance objective: maximize posterior_mu' * w - 0.5 * lambda * w' * Sigma * w. Prior Risk Aversion builds the return forecast; Optimizer Risk Aversion sizes the portfolio from that forecast.`,
  blackLittermanMaxWeight: `Description: Optional max-weight cap used only by Black-Litterman.
Model impact: If filled, this overrides Default Max Weight for the Black-Litterman row.
Details: Leave blank to use Default Max Weight.`,
  lookbackDays: `Description: Number of most recent rows used by the portfolio optimizer when Use All History is off.
Model impact: This controls the optimizer's estimation window for returns, volatility, covariance, drawdowns, VaR, CVaR, and target weights. It uses the most recent rows available after any Data Since refresh.
Details: Shorter windows adapt faster but are noisier. Longer windows are more stable but may dilute recent regime changes. This is an estimation window, not a periodic rebalance frequency.`,
  useAllHistory: `Description: Uses every available cached observation for the selected portfolio universe.
Model impact: This disables the numeric lookback window and bases optimization metrics on the full available history after data cleaning. Selected-stock runs use the true common overlap; entire-universe runs can exclude thin-history names so missing pre-listing returns are not treated as 0 percent.
Details: Turn this off when you want Data Since to define available history but Lookback to define the recent optimizer estimation window.`,
  builderDataStart: `Description: Earliest date requested when the portfolio builder auto-downloads or refreshes history.
Model impact: Earlier dates can increase the amount of data available for portfolio statistics and optimization.
Details: This only affects a data fetch. If Refresh History is off and all selected symbols are already cached, the builder uses the local cache and Data Since does not trim the optimizer window. Use Lookback or Use All History for that.`,
  autoDownloadMissing: `Description: Allows the builder to fetch missing symbols before optimizing.
Model impact: When enabled, typed tickers that are not already cached can still be included if the provider returns valid data.
Details: Turn this off for fully offline experiments or when you want the builder to use only the existing cache.`,
  refreshHistory: `Description: Forces the builder to refresh price history for the selected symbols instead of only filling missing names.
Model impact: This can change returns, risk estimates, and weights if cached data was stale or incomplete. It updates the available price history; Use All History or Lookback then controls how much of that refreshed history is used for optimization.
Details: Leave this off for normal cached builds. Turn it on only when you intentionally want to call Yahoo/Stooq and update the stored price cache before optimizing.`,
  modeSeg: `Description: Switches the dashboard between dark and light theme modes.
Model impact: This does not change any trading model, backtest, optimizer, or saved market data.
Details: It only changes the visual base theme and is saved locally in the browser.`,
  presetSwatches: `Description: Applies a predefined accent color pair to the interface.
Model impact: This does not change strategy calculations or portfolio results.
Details: Presets update buttons, highlights, chart colors, and progress styling for readability and preference.`,
  colorGrid: `Description: Customizes the dashboard color variables manually.
Model impact: This affects only the visual interface, not model calculations.
Details: Chart colors update immediately so equity, drawdown, gains, and losses remain visually consistent with the selected palette.`,
  "--accent": `Description: Primary accent color for the dashboard.
Model impact: Visual only. It changes highlights, active controls, chart accents, and progress bars without changing data or model results.
Details: Pick a color with enough contrast against the current theme.`,
  "--accent-2": `Description: Secondary accent color used in gradients and supporting highlights.
Model impact: Visual only. It does not alter backtests, signals, or portfolio weights.
Details: Works best as a complementary color to the primary accent.`,
  "--gain": `Description: Color used for positive returns, gains, and favorable values.
Model impact: Visual only. It helps distinguish profitable or positive metrics without changing calculations.
Details: Keep it clearly different from the loss color.`,
  "--loss": `Description: Color used for drawdowns, losses, negative returns, VaR, and CVaR.
Model impact: Visual only. It helps identify downside risk and negative values without changing calculations.
Details: Choose a color that remains legible in both dark and light mode.`,
  toggleAurora: `Description: Toggles the ambient background glow.
Model impact: Visual only. It does not change strategy, optimizer, or data behavior.
Details: Turn it off if you prefer a flatter workstation-style dashboard.`,
  toggleMotion: `Description: Toggles page transition motion.
Model impact: Visual only. It does not change calculations or data.
Details: Turning it off reduces interface animation and can make the app feel more static.`,
  resetTheme: `Description: Restores the default dashboard palette.
Model impact: Visual only. It does not reset data, strategy settings, portfolio settings, or reports.
Details: Use this if custom colors reduce readability.`,
  curveRange: `Description: Chooses the visible zoom range for the equity and drawdown charts.
Model impact: This does not rerun the backtest or change metrics. It only changes the portion of the already computed curve shown on screen.
Details: Use Full for the complete test and shorter windows for recent behavior.`,
  portfolioBuilderTitle: `Description: Controls the custom portfolio research run.
Model impact: These inputs define the investable universe, return model, capital base, data source, estimation window, and per-optimizer parameters used by the optimizer suite directly below this form.
Details: This builder is separate from the saved signal backtest. Use it when you want to test a specific stock list or let the optimizer search the local universe under your current settings.`,
  currentBuilderSuiteTitle: `Description: Shows the optimizer suite generated from the current Portfolio Builder settings.
Model impact: Every row uses the same symbols, return model, date window, and initial equity, while each optimizer can use its own risk or cap parameters.
Details: The highlighted row is the automatically recommended Best Sharpe result; all optimizer rows are calculated together every time.`,
  optimizerWeightsTitle: `Description: Collapsible weight breakdown for each optimizer type.
Model impact: These are the actual target allocations produced by each optimizer. Expand a portfolio type to inspect its symbols, weights, and dollar allocation based on Initial Equity.
Details: Groups are sorted in the same order as the optimizer metrics table, with the recommended Best Sharpe optimizer opened by default.`,
  savedSignalUniverseTitle: `Description: Saved universe-level optimizer suite from the latest signal/data pipeline run.
Model impact: This table is built from the overnight return matrix created when Market Data or Signal Backtest last ran, so its symbols, date range, and observations can differ from the current builder form.
Details: Use it as a broad universe diagnostic. Use Current Builder Optimizer Suite for the specific settings you just submitted.`,
  downloadBuilderSummaryCsv: `Description: Downloads the current builder optimizer metrics as a CSV file.
Model impact: This does not rerun or alter the model. It exports the rows currently produced by the latest portfolio build.
Details: Includes the selected flag, builder date window, return model, observations, performance ratios, risk metrics, Invested, Cash, Max Weight, and positions.`,
  downloadBuilderWeightsCsv: `Description: Downloads all current builder optimizer weights as a CSV file.
Model impact: This does not change weights or performance. It exports every symbol allocation for every optimizer type in the latest builder run.
Details: Use this for audit, portfolio construction, or outside analysis when the collapsible UI is too compact.`,
  downloadTradesCsv: `Description: Downloads Trade Blotter executions for the active date, symbol, and PnL filters.
Model impact: Export only. It does not rerun the signal backtest or alter the trade history.
Details: The CSV includes all matching filtered rows, not just the visible table slice.`,
};

const PORTFOLIO_HEADER_HELP = {
  Portfolio: `Description: Name of the optimizer style.
Model impact: Each style uses a different allocation rule, so this is the key grouping variable for comparing results.
Details: The highlighted row is the automatically recommended Best Sharpe result; all optimizer rows are calculated together.`,
  Start: `Description: First return observation used in the metric calculation.
Model impact: Earlier starts can materially change expected return, covariance, drawdown, VaR, CVaR, and rolling ratios.
Details: This may differ between the current builder and saved universe suite because they can use different symbol sets and data windows.`,
  End: `Description: Last return observation used in the metric calculation.
Model impact: This controls the final date included in returns, ending equity, drawdown, and rolling ratios.
Details: A stale end date means the underlying data cache or signal run has not been refreshed through the latest available session.`,
  Years: `Description: Calendar years elapsed between Start and End.
Model impact: Used to annualize CAGR-style metrics. Short windows can make annualized values look exaggerated.
Details: When there is less than roughly one trading year, CAGR and Calmar are intentionally blanked in the builder output.`,
  Obs: `Description: Number of return rows used by the optimizer metrics.
Model impact: More observations usually stabilize volatility, covariance, VaR, CVaR, and rolling ratio estimates.
Details: This is the cleaned overlapping history after missing-data alignment, not necessarily the raw price row count.`,
  "Initial Equity": `Description: Starting account value used to scale dollar outputs.
Model impact: Changes Ending Equity and allocation dollars, but not percentage returns, weights, Sharpe, Sortino, Calmar, VaR percent, or CVaR percent.
Details: Use this to compare dollar impacts under different capital assumptions.`,
  "Ending Equity": `Description: Final compounded equity after applying the portfolio return stream.
Model impact: This is an output, not an input. It reflects the selected history, return model, weights, and initial equity.
Details: It includes cash drag when low max-weight caps leave capital uninvested.`,
  "Period Return": `Description: Total return over the displayed Start-to-End period.
Model impact: Output only. It shows realized compounded return for that optimizer on the chosen return matrix.
Details: This is not annualized; compare it alongside Years and CAGR/Ann Return.`,
  CAGR: `Description: Compounded annual growth rate over the elapsed calendar period.
Model impact: Output only. It annualizes total compounded return and is sensitive to short or partial-year windows.
Details: Blank values mean the history is too short for a stable CAGR display.`,
  "Ann Return": `Description: Average periodic return annualized using 252 trading days.
Model impact: Output only. It can differ from CAGR because it annualizes average returns rather than full compounding.
Details: Use it with Annual Vol, Sharpe, and Sortino.`,
  "Annual Vol": `Description: Annualized standard deviation of daily portfolio returns.
Model impact: Output only, but it is central to Sharpe and many risk comparisons.
Details: Lower max-weight caps can lower volatility by leaving more cash uninvested.`,
  Sharpe: `Description: Annualized excess return divided by annualized volatility.
Model impact: Output only. The Best Sharpe recommendation uses this family of risk-adjusted return logic.
Details: Higher is better, but very short windows can overstate it.`,
  Sortino: `Description: Annualized excess return divided by downside deviation.
Model impact: Output only. It penalizes downside volatility more than upside volatility.
Details: Useful when you care more about negative return variability than total volatility.`,
  Calmar: `Description: CAGR divided by absolute max drawdown.
Model impact: Output only. It measures return relative to worst peak-to-trough loss.
Details: Blank values can occur when the window is too short or there is no meaningful drawdown.`,
  "1Y Sharpe": `Description: Rolling Sharpe over the most recent one-year window.
Model impact: Output only. It highlights recent risk-adjusted behavior.
Details: Blank if fewer than 252 observations are available.`,
  "3Y Sharpe": `Description: Rolling Sharpe over the most recent three-year window.
Model impact: Output only. It smooths recent behavior across a broader regime.
Details: Blank if fewer than 756 observations are available.`,
  "5Y Sharpe": `Description: Rolling Sharpe over the most recent five-year window.
Model impact: Output only. It is useful for long-run stability checks.
Details: Blank if fewer than 1,260 observations are available.`,
  "1Y Sortino": `Description: Rolling Sortino over the most recent one-year window.
Model impact: Output only. It focuses on recent downside-adjusted return.
Details: Blank if there is not enough recent history.`,
  "3Y Sortino": `Description: Rolling Sortino over the most recent three-year window.
Model impact: Output only. It smooths downside-adjusted performance across several market regimes.
Details: Blank if there is not enough recent history.`,
  "5Y Sortino": `Description: Rolling Sortino over the most recent five-year window.
Model impact: Output only. It helps identify long-term downside-adjusted consistency.
Details: Blank if there is not enough recent history.`,
  "1Y Calmar": `Description: Rolling Calmar over the most recent one-year window.
Model impact: Output only. It compares recent compounded return to recent drawdown.
Details: Blank if there is not enough history or no meaningful drawdown.`,
  "3Y Calmar": `Description: Rolling Calmar over the most recent three-year window.
Model impact: Output only. It compares medium-term compounded return to drawdown.
Details: Blank if there is not enough history or no meaningful drawdown.`,
  "5Y Calmar": `Description: Rolling Calmar over the most recent five-year window.
Model impact: Output only. It compares long-term compounded return to drawdown.
Details: Blank if there is not enough history or no meaningful drawdown.`,
  "Max DD": `Description: Worst peak-to-trough equity drawdown in the test window.
Model impact: Output only. It drives Calmar and helps compare path risk.
Details: More negative values mean deeper drawdowns.`,
  "Win Rate": `Description: Percentage of return observations above zero.
Model impact: Output only. It summarizes hit rate but ignores gain/loss size.
Details: Use with Profit Factor and drawdown metrics for fuller context.`,
  "Profit Factor": `Description: Sum of positive returns divided by absolute sum of negative returns.
Model impact: Output only. It compares gross wins to gross losses.
Details: Blank can mean there were no losses in the selected window.`,
  "VaR 95": `Description: Historical 5th percentile daily return.
Model impact: Output only. It estimates a one-day downside threshold from historical returns.
Details: More negative values imply worse typical tail risk.`,
  "CVaR 95": `Description: Average daily return in the worst 5 percent of outcomes.
Model impact: Output only. It is a deeper tail-risk estimate than VaR.
Details: CVaR Aware uses this tail-risk idea when selecting weights.`,
  "Cost Drag": `Description: Sum of modeled transaction cost returns over the test window.
Model impact: Higher fees, slippage, exposure, or turnover increase this value and reduce net returns.
Details: Signal Backtest charges daily overnight round trips. Portfolio Research charges the initial allocation, rebalance turnover, and the daily drift-rebalancing implied by holding fixed weights against moving prices — each stock billed at its own volatility-scaled rate.`,
  Invested: `Description: Sum of portfolio weights actually deployed.
Model impact: Lower max-weight caps can make this less than 100 percent, leaving the rest in cash.
Details: This is why a 1 percent max weight across 8 names invests up to 8 percent and leaves roughly 92 percent cash.`,
  Cash: `Description: Uninvested portfolio weight after optimizer caps are applied.
Model impact: Cash earns zero return in this model, lowering both expected return and volatility.
Details: High cash is expected when Max Weight is very low or Kelly is fractional.`,
  Cap: `Description: Max-weight limit applied to this optimizer row.
Model impact: This can come from Default Max Weight or from that optimizer's individual cap override.
Details: Max Weight should be less than or equal to Cap unless the row is empty or fully cash-constrained.`,
  "Max Weight": `Description: Largest single-symbol allocation in the optimizer output.
Model impact: Shows whether the optimizer is constrained by the max-weight input.
Details: It should not exceed the Cap shown for that same optimizer row.`,
  Rebalances: `Description: Number of times weights were recalculated in the Portfolio Research run.
Model impact: Static runs show zero. Monthly, quarterly, and annual runs show how many rebalance snapshots were applied to the performance path.
Details: More frequent rebalancing adapts faster but can create more turnover.`,
  "Avg Turnover": `Description: Average absolute weight change on rebalance dates.
Model impact: Higher turnover means the portfolio is changing more aggressively between rebalance periods and will create more cost drag when Portfolio Research fees or slippage are above zero.
Details: A value of 20 percent means the average rebalance changed about 20 percent of portfolio weight.`,
  Positions: `Description: Number of symbols with non-zero target weight.
Model impact: Higher position counts usually diversify idiosyncratic risk, while lower counts concentrate exposure.
Details: This is calculated after missing-data alignment and weight filtering.`,
  Symbol: `Description: Stock ticker receiving a non-zero target allocation.
Model impact: Symbols define the actual holdings the optimizer would use for that portfolio type.
Details: Expand each portfolio group to inspect which names survived the optimizer and max-weight cap.`,
  Weight: `Description: Target portfolio weight for the symbol.
Model impact: Higher weights mean more capital is allocated to that name, bounded by the Max Weight control.
Details: In low-cap runs, each name may be capped at 1 percent or another small limit, with the rest in cash.`,
  Allocation: `Description: Dollar allocation implied by Weight and Initial Equity.
Model impact: Output only. It scales with Initial Equity but does not change percentage weights or returns.
Details: Useful for turning model weights into executable notional targets.`,
};

const TRADE_HEADER_HELP = {
  "Entry Date": `Description: The signal date — the close at which the position is bought.
Model impact: This is the date the stock's overnight signal rank qualified it for the book.
Details: The position is held from this close to the next session's close.`,
  "Exit Date": `Description: The date the position is sold at the close.
Model impact: Gross PnL is measured close-to-close across this overnight holding period.
Details: Usually the next trading session after Entry Date; weekends and holidays stretch the gap.`,
  Rank: `Description: The stock's signal rank on the entry date — 1 is the strongest overnight candidate.
Model impact: Only ranks up to the Top N control are traded, so rank decides membership in the book.
Details: Rank comes from rolling overnight Sharpe over the signal lookback window.`,
  Ticker: `Description: The stock symbol traded.
Model impact: Filter the blotter by symbol to audit one name's trade history.
Details: Use the Symbol filter above; it matches substrings, so AA also matches AAPL.`,
  "Target Weight": `Description: Fraction of total equity assigned to this position.
Model impact: Controlled by the Top N and Max Weight settings in the Signal Backtest tab.
Details: 0.07 means 7 percent of current equity was committed to this overnight trade.`,
  "Overnight Return": `Description: The stock's close-to-close return over the holding period.
Model impact: This is the raw market outcome before any transaction costs.
Details: Overnight Return × Notional = Gross PnL.`,
  Notional: `Description: Dollar size of the position — Target Weight × current equity.
Model impact: Scales with the Initial Equity control; percentage results are unaffected.
Details: Both gross PnL and cost are computed from this dollar base.`,
  "Gross PnL": `Description: Profit or loss before transaction costs.
Model impact: Notional × Overnight Return.
Details: Compare against Cost to see how much of each trade the friction consumes.`,
  Cost: `Description: Transaction cost charged on this trade in dollars.
Model impact: Notional × era cost rate — the historical model charges much higher bps in early decades.
Details: With the flat model, Cost = Notional × (fees + slippage) in bps, applied per side.`,
  "Net PnL": `Description: Profit or loss after costs — Gross PnL − Cost.
Model impact: This is what actually compounds into the equity curve.
Details: Filter to Losers to see where net PnL is negative.`,
  "O/N Sharpe": `Description: The stock's rolling overnight Sharpe at the time of the signal.
Model impact: This is the score the ranking is based on — higher means a more consistent overnight record.
Details: Computed over the signal lookback window set in the Signal Backtest tab.`,
};

const BENCHMARK_HEADER_HELP = {
  Benchmark: `Description: The comparison index for this row.
Model impact: All relative statistics (beta, alpha, capture) are measured against this series.
Details: MSCI World is proxied by the URTH ETF from 2012; US 10Y Treasury is approximated from the ^TNX yield.`,
  Obs: `Description: Number of overlapping daily observations between the strategy and this benchmark.
Model impact: Fewer observations make beta, alpha, and correlation less reliable.
Details: MSCI World has far fewer observations because its proxy only starts in 2012.`,
  "Strat CAGR": `Description: Strategy compounded annual growth rate over the overlap window.
Model impact: Output only. Recomputed over exactly the dates where the benchmark exists.
Details: This can differ from the headline CAGR on the Signal Backtest tab because the window is clipped to the benchmark overlap.`,
  "Bench CAGR": `Description: The benchmark's compounded annual growth rate over the overlap window.
Model impact: The yardstick for whether the strategy beat passive exposure.
Details: Compare on the same row only — different rows cover different windows.`,
  "Bench Sharpe": `Description: The benchmark's annualized Sharpe ratio over the overlap window.
Model impact: Shows whether the strategy's risk-adjusted edge beats simply holding the index.
Details: Risk-free rate is 0 unless configured otherwise.`,
  "Bench Max DD": `Description: The benchmark's worst peak-to-trough drawdown over the overlap window.
Model impact: Compare against the strategy's Max DD to judge relative path risk.
Details: More negative means a deeper loss from the peak.`,
  Corr: `Description: Correlation between daily strategy and benchmark returns.
Model impact: Near 1 means the strategy is basically the index; near 0 means genuinely diversifying.
Details: Overnight strategies typically show low correlation, which is part of their appeal.`,
  Beta: `Description: Sensitivity of strategy returns to benchmark returns.
Model impact: Beta of 0.5 means the strategy tends to move half as much as the benchmark.
Details: Computed by regression of daily strategy returns on daily benchmark returns.`,
  "Alpha (ann.)": `Description: Annualized return the strategy adds beyond what beta exposure to the benchmark explains.
Model impact: Positive alpha means the edge is not just disguised market exposure.
Details: Regression intercept, annualized.`,
  "Info Ratio": `Description: Active return divided by tracking error.
Model impact: Measures consistency of outperformance, not just its size.
Details: Above ~0.5 is generally considered good for an active strategy.`,
  "Up Capture": `Description: How much of the benchmark's up-day return the strategy captures.
Model impact: Above 100 percent means the strategy gains more than the benchmark on its good days.
Details: Best read together with Down Capture.`,
  "Down Capture": `Description: How much of the benchmark's down-day return the strategy suffers.
Model impact: Below 100 percent means the strategy loses less on the benchmark's bad days.
Details: A good profile is high Up Capture with low Down Capture.`,
};

const WALKFORWARD_HEADER_HELP = {
  Fold: `Description: Sequential index of the walk-forward split.
Model impact: Each fold re-fits parameters on its own training window — no fold sees the future.
Details: More folds give a richer picture of parameter stability across eras.`,
  Train: `Description: The in-sample window used to pick parameters for this fold.
Model impact: Lookback and Top N are chosen to maximize the selection metric over these dates only.
Details: Controlled by the Train Days input.`,
  Test: `Description: The out-of-sample window where those frozen parameters are scored.
Model impact: These results are the honest estimate — the model never saw this data when choosing parameters.
Details: Controlled by the Test Days input; windows step forward by Step Days.`,
  Lookback: `Description: The signal lookback chosen on the training window.
Model impact: Shows whether the optimal lookback is stable or jumps around between eras.
Details: Large swings fold-to-fold suggest the signal is regime-sensitive.`,
  "Top N": `Description: The book size chosen on the training window.
Model impact: Shows whether concentration or diversification was favored in each era.
Details: Chosen from the candidate grid by the selection metric.`,
  "Train Score": `Description: The in-sample selection metric value achieved by the chosen parameters.
Model impact: This is the optimistic number — expect the OOS columns to be weaker.
Details: The gap between Train Score and OOS Sharpe is the overfitting tax.`,
  "OOS Sharpe": `Description: Out-of-sample Sharpe on the test window with frozen parameters.
Model impact: The single most honest performance number on this dashboard.
Details: Consistently positive OOS Sharpe across folds is the real evidence of an edge.`,
  "OOS CAGR": `Description: Out-of-sample compounded annual growth on the test window.
Model impact: Return actually earned by frozen parameters on unseen data.
Details: Annualized, so short test windows can exaggerate it.`,
  "OOS Max DD": `Description: Worst peak-to-trough drawdown during the out-of-sample test window.
Model impact: Shows the pain you would have felt trading parameters picked on prior data.
Details: More negative means a deeper loss within that fold's test window.`,
};

let activeHelpAnchor = null;
let pinnedHelpAnchor = null;

function ensureHelpTooltip() {
  let tooltip = document.getElementById("inputHelpTooltip");
  if (!tooltip) {
    tooltip = document.createElement("div");
    tooltip.id = "inputHelpTooltip";
    tooltip.setAttribute("role", "tooltip");
    tooltip.hidden = true;
    document.body.appendChild(tooltip);
  }
  return tooltip;
}

function positionHelpTooltip(anchor) {
  const tooltip = ensureHelpTooltip();
  if (tooltip.hidden) return;
  const rect = anchor.getBoundingClientRect();
  const margin = 12;
  const width = Math.min(380, window.innerWidth - margin * 2);
  tooltip.style.width = `${width}px`;
  const measured = tooltip.getBoundingClientRect();
  const left = Math.min(
    Math.max(rect.left + rect.width / 2 - measured.width / 2, margin),
    window.innerWidth - measured.width - margin,
  );
  let top = rect.bottom + 10;
  let placement = "bottom";
  if (top + measured.height > window.innerHeight - margin) {
    top = Math.max(margin, rect.top - measured.height - 10);
    placement = "top";
  }
  tooltip.dataset.placement = placement;
  tooltip.style.left = `${left}px`;
  tooltip.style.top = `${top}px`;
}

function showHelpTooltip(anchor) {
  const tooltip = ensureHelpTooltip();
  tooltip.replaceChildren();
  String(anchor.dataset.helpText || "")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .forEach((line) => {
      const paragraph = document.createElement("p");
      paragraph.textContent = line;
      tooltip.appendChild(paragraph);
    });
  tooltip.hidden = false;
  activeHelpAnchor = anchor;
  window.requestAnimationFrame(() => positionHelpTooltip(anchor));
}

function hideHelpTooltip(force = false) {
  if (!force && pinnedHelpAnchor) return;
  const tooltip = ensureHelpTooltip();
  tooltip.hidden = true;
  activeHelpAnchor = null;
  if (force) pinnedHelpAnchor = null;
  document.querySelectorAll(".input-help.pinned").forEach((node) => node.classList.remove("pinned"));
}

function createHelpIcon(key, text) {
  const icon = document.createElement("span");
  icon.className = "input-help";
  icon.dataset.helpKey = key;
  icon.dataset.helpText = text;
  icon.tabIndex = 0;
  icon.setAttribute("role", "button");
  icon.setAttribute("aria-label", "Explain this input");
  icon.innerHTML = `
    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <circle cx="12" cy="12" r="9"></circle>
      <path d="M12 10v7"></path>
      <path d="M12 7h.01"></path>
    </svg>
  `;
  icon.addEventListener("mouseenter", () => showHelpTooltip(icon));
  icon.addEventListener("mouseleave", () => {
    if (pinnedHelpAnchor !== icon) hideHelpTooltip();
  });
  icon.addEventListener("focus", () => showHelpTooltip(icon));
  icon.addEventListener("blur", () => {
    if (pinnedHelpAnchor !== icon) hideHelpTooltip();
  });
  icon.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    if (pinnedHelpAnchor === icon) {
      hideHelpTooltip(true);
      return;
    }
    hideHelpTooltip(true);
    pinnedHelpAnchor = icon;
    icon.classList.add("pinned");
    showHelpTooltip(icon);
  });
  return icon;
}

function attachHelpIconWithText(target, key, text) {
  if (!target || !text || target.querySelector(`.input-help[data-help-key="${key}"]`)) return;
  if (target.tagName === "TH") {
    const label = target.textContent.trim();
    target.textContent = "";
    const wrapper = document.createElement("span");
    wrapper.className = "th-help-label label-with-help";
    wrapper.appendChild(document.createTextNode(label));
    wrapper.appendChild(createHelpIcon(key, text));
    target.appendChild(wrapper);
    return;
  }
  target.classList.add("label-with-help");
  target.appendChild(createHelpIcon(key, text));
}

function attachHelpIcon(target, key) {
  attachHelpIconWithText(target, key, HELP_TEXT[key]);
}

function labelTargetForControl(control) {
  const label = control?.closest("label");
  if (!label) return null;
  if (label.classList.contains("switch")) return label.querySelector(".switch-label");
  if (label.classList.contains("color-field")) return label.querySelector(".cf-name");
  const directSpans = [...label.children].filter((child) => child.tagName === "SPAN" && !child.classList.contains("track"));
  return directSpans[0] || null;
}

function decorateHelpTargets() {
  Object.keys(HELP_TEXT).forEach((key) => {
    const control = document.getElementById(key);
    if (control) attachHelpIcon(labelTargetForControl(control), key);
  });
  document.querySelectorAll("#colorGrid input[type='color']").forEach((input) => {
    attachHelpIcon(labelTargetForControl(input), input.dataset.var);
  });
  attachHelpIcon(document.querySelector("#modeSeg")?.closest(".setting-row")?.querySelector("strong"), "modeSeg");
  attachHelpIcon(document.querySelector("#presetSwatches")?.closest(".setting-row")?.querySelector("strong"), "presetSwatches");
  attachHelpIcon(document.querySelector("#colorGrid")?.closest(".setting-row")?.querySelector("strong"), "colorGrid");
  attachHelpIcon(document.querySelector("#resetTheme")?.closest(".setting-row")?.querySelector("strong"), "resetTheme");
  const curveTitle = document.querySelector(".curve-header h2");
  attachHelpIcon(curveTitle, "curveRange");
  [
    "portfolioBuilderTitle",
    "optimizerSettingsTitle",
    "currentBuilderSuiteTitle",
    "optimizerWeightsTitle",
    "savedSignalUniverseTitle",
    "downloadBuilderSummaryCsv",
    "downloadBuilderWeightsCsv",
    "downloadTradesCsv",
    "optimizeCandidatesButton",
  ].forEach((key) => attachHelpIcon(document.getElementById(key), key));
  decoratePortfolioHeaderHelp();
}

function decorateTableHeaderHelp(targets) {
  targets.forEach(({ bodyId, dict, prefix }) => {
    const headers = document.getElementById(bodyId)?.closest("table")?.querySelectorAll("thead th") || [];
    headers.forEach((header) => {
      const label = header.textContent.trim();
      attachHelpIconWithText(header, `${prefix}-${label.replace(/\W+/g, "-").toLowerCase()}`, dict[label]);
    });
  });
}

function decoratePortfolioHeaderHelp() {
  decorateTableHeaderHelp([
    { bodyId: "builderSummaryBody", dict: PORTFOLIO_HEADER_HELP, prefix: "portfolio-header" },
    { bodyId: "portfolioBody", dict: PORTFOLIO_HEADER_HELP, prefix: "portfolio-header" },
    { bodyId: "tradesBody", dict: TRADE_HEADER_HELP, prefix: "trade-header" },
    { bodyId: "benchmarkBody", dict: BENCHMARK_HEADER_HELP, prefix: "benchmark-header" },
    { bodyId: "walkforwardBody", dict: WALKFORWARD_HEADER_HELP, prefix: "walkforward-header" },
  ]);
}

document.addEventListener("click", (event) => {
  const target = event.target instanceof Element ? event.target : null;
  if (!target || (!target.closest(".input-help") && !target.closest("#inputHelpTooltip"))) {
    hideHelpTooltip(true);
  }
});
window.addEventListener("scroll", () => {
  if (activeHelpAnchor) positionHelpTooltip(activeHelpAnchor);
}, true);
window.addEventListener("resize", () => {
  if (activeHelpAnchor) positionHelpTooltip(activeHelpAnchor);
});

window.decorateHelpTargets = decorateHelpTargets;

const taskProgressTimers = new Map();

function clampPercent(value) {
  return Math.min(100, Math.max(0, Number(value) || 0));
}

function clearTaskProgressTimer(id) {
  const task = taskProgressTimers.get(id);
  if (task?.timer) {
    window.clearInterval(task.timer);
    taskProgressTimers.delete(id);
  }
}

function setTaskProgressPercent(node, percent) {
  const value = clampPercent(percent);
  const fillNode = node.querySelector(".task-progress-fill");
  const percentNode = node.querySelector("[data-progress-percent]");
  const trackNode = node.querySelector(".task-progress-track");
  node.dataset.progressPercent = String(value);
  if (fillNode) fillNode.style.width = `${value}%`;
  if (percentNode) percentNode.textContent = `${Math.round(value)}%`;
  if (trackNode) trackNode.setAttribute("aria-valuenow", String(Math.round(value)));
}

function updateTaskProgress(id, percent, label) {
  const node = document.getElementById(id);
  if (!node) return;
  const labelNode = node.querySelector("[data-progress-label]");
  if (labelNode && label) labelNode.textContent = label;
  setTaskProgressPercent(node, percent);
  const task = taskProgressTimers.get(id);
  if (task) task.percent = clampPercent(percent);
}

function startTaskProgress(id, label, options = {}) {
  const node = document.getElementById(id);
  if (!node) return;
  const labelNode = node.querySelector("[data-progress-label]");
  const runId = `${Date.now()}-${Math.random()}`;
  const initial = clampPercent(options.initial ?? 4);
  const ceiling = clampPercent(options.ceiling ?? 92);
  node.dataset.progressRun = runId;
  node.hidden = false;
  node.classList.remove("success", "failed");
  node.classList.add("active");
  if (labelNode) labelNode.textContent = label;
  clearTaskProgressTimer(id);
  setTaskProgressPercent(node, initial);
  const task = { percent: initial, timer: null };
  task.timer = window.setInterval(() => {
    const remaining = Math.max(ceiling - task.percent, 0);
    const step = Math.max(0.35, remaining * 0.035);
    task.percent = Math.min(ceiling, task.percent + step);
    setTaskProgressPercent(node, task.percent);
  }, 450);
  taskProgressTimers.set(id, task);
}

function finishTaskProgress(id, label, failed = false) {
  const node = document.getElementById(id);
  if (!node) return;
  const labelNode = node.querySelector("[data-progress-label]");
  const runId = node.dataset.progressRun || "";
  const task = taskProgressTimers.get(id);
  const currentPercent = task?.percent ?? Number(node.dataset.progressPercent || 0);
  clearTaskProgressTimer(id);
  node.classList.remove("active", "success", "failed");
  node.classList.add(failed ? "failed" : "success");
  setTaskProgressPercent(node, failed ? currentPercent : 100);
  if (labelNode && label) labelNode.textContent = label;
  window.setTimeout(() => {
    if (node.dataset.progressRun === runId && !node.classList.contains("active")) {
      node.hidden = true;
      node.classList.remove("success", "failed");
    }
  }, failed ? 1800 : 1200);
}

const TAB_TITLES = {
  overview: "Overview",
  signal: "Signal Backtest",
  evaluation: "Evaluation",
  portfolio: "Portfolio Research",
  trades: "Trade Blotter",
  findings: "Research Findings",
  system: "System",
};

// Merged tabs show one member panel at a time; these are their default views.
const TAB_SUBPANELS = {
  evaluation: "benchmarks",
  system: "data",
};

function activateSubpanel(tab, sub) {
  document.querySelectorAll(`[data-tab-panel="${tab}"]`).forEach((panel) => {
    panel.classList.toggle("active", panel.dataset.subpanel === sub);
  });
  document
    .querySelectorAll(`[data-tab-panel="${tab}"] .subnav-item`)
    .forEach((button) => button.classList.toggle("active", button.dataset.subtab === sub));
  // Charts living in a freshly shown panel were sized while hidden; repaint them.
  window.requestAnimationFrame(resizeInteractiveCharts);
}

function activateTab(tab) {
  document.querySelectorAll("[data-tab]").forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === tab);
  });
  document.querySelectorAll("[data-tab-panel]").forEach((panel) => {
    panel.classList.toggle("active", panel.dataset.tabPanel === tab);
  });
  if (TAB_SUBPANELS[tab]) {
    activateSubpanel(tab, TAB_SUBPANELS[tab]);
  }
  const title = document.getElementById("pageTitle");
  if (title && TAB_TITLES[tab]) title.textContent = TAB_TITLES[tab];
  if (tab === "signal") {
    window.requestAnimationFrame(renderCurves);
  }
  if (tab === "findings" && !state.eraStudyLoaded) {
    loadEraStudy().catch((error) => toast(error.message));
  }
  window.requestAnimationFrame(resizeInteractiveCharts);
}

function setNumberInput(id, value) {
  const input = document.getElementById(id);
  if (input && value !== null && value !== undefined) {
    input.value = String(value);
  }
}

function syncBacktestControls(strategy) {
  if (!strategy) return;
  setNumberInput("signalInitialEquity", strategy.initial_capital);
  setNumberInput("signalFeesBps", strategy.fees_bps);
  setNumberInput("signalSlippageBps", strategy.slippage_bps);
  setNumberInput("signalLookbackDays", strategy.lookback_days);
  setNumberInput("signalMinHistory", strategy.min_history);
  setNumberInput("signalTopN", strategy.top_n);
  setNumberInput("signalMaxWeight", strategy.max_weight);
  setNumberInput("signalMinSignal", strategy.min_signal);
  if (strategy.cost_model) {
    const select = document.getElementById("signalCostModel");
    if (select) select.value = strategy.cost_model.mode || "flat";
  }
  setNumberInput("signalCapitalCapacity", strategy.capital_capacity || 0);
  setNumberInput("signalCashRate", (strategy.cash_rate || 0) * 100);
  setNumberInput("signalAdvParticipation", (strategy.max_adv_participation || 0) * 100);
}

function backtestPayload() {
  const capacity = Number(document.getElementById("signalCapitalCapacity").value || 0);
  const cashRatePct = Number(document.getElementById("signalCashRate").value || 0);
  const advPct = Number(document.getElementById("signalAdvParticipation").value || 0);
  return {
    initial_capital: Number(document.getElementById("signalInitialEquity").value || 1000000),
    fees_bps: Number(document.getElementById("signalFeesBps").value || 0),
    slippage_bps: Number(document.getElementById("signalSlippageBps").value || 0),
    lookback_days: Number(document.getElementById("signalLookbackDays").value || 63),
    min_history: Number(document.getElementById("signalMinHistory").value || 40),
    top_n: Number(document.getElementById("signalTopN").value || 25),
    max_weight: Number(document.getElementById("signalMaxWeight").value || 0.07),
    min_signal: Number(document.getElementById("signalMinSignal").value || 0),
    cost_model: document.getElementById("signalCostModel").value || "flat",
    capital_capacity: capacity > 0 ? capacity : null,
    cash_rate: cashRatePct / 100,
    max_adv_participation: advPct > 0 ? advPct / 100 : null,
    price_start: document.getElementById("signalPriceStart").value || null,
    price_end: document.getElementById("signalPriceEnd").value || null,
    price_symbols: document.getElementById("signalPriceTickers").value || null,
  };
}

function renderSurvivorship(survivorship) {
  const banner = document.getElementById("survivorshipBanner");
  if (!banner) return;
  const warning = survivorship && survivorship.warning;
  if (!warning) {
    banner.hidden = true;
    return;
  }
  banner.hidden = false;
  banner.classList.toggle("info", Boolean(survivorship.point_in_time));
  banner.textContent = survivorship.point_in_time
    ? `Point-in-time index membership active. ${warning}`
    : `Survivorship bias warning: ${warning}`;
}

function renderOverviewHome(overview) {
  const grid = document.getElementById("overviewStatGrid");
  if (!grid) return;
  const metrics = overview.metrics || {};
  const dataWindow = overview.data_window || {};
  const tradeSummary = state.tradeSummary || {};
  const stats = [
    ["Price Window", dataWindow.start && dataWindow.end ? `${dataWindow.start} → ${dataWindow.end}` : "-"],
    ["Universe", dataWindow.symbol_count ? `${Number(dataWindow.symbol_count).toLocaleString()} symbols` : "-"],
    ["Signals", tradeSummary.source_total_trades != null ? Number(tradeSummary.source_total_trades).toLocaleString() : "-"],
    ["Ending Equity", metrics.final_equity != null ? formatCompactMoney(metrics.final_equity) : "-"],
    ["Sharpe", metrics.sharpe != null ? formatNumber(metrics.sharpe) : "-"],
    ["Max Drawdown", metrics.max_drawdown != null ? formatPct(metrics.max_drawdown) : "-"],
  ];
  grid.replaceChildren();
  stats.forEach(([label, value]) => {
    const tile = document.createElement("article");
    tile.className = "metric";
    tile.innerHTML = `
      <div class="metric-label">${label}</div>
      <div class="metric-value">${value}</div>
    `;
    grid.appendChild(tile);
  });
  const note = document.getElementById("overviewDataNote");
  const survivorship = overview.survivorship || {};
  if (note) {
    const windowText = dataWindow.start
      ? `Cache covers ${dataWindow.start} to ${dataWindow.end}.`
      : "No price cache yet — run a download in System → Market Data.";
    let clampText = "";
    if (dataWindow.requested_start && dataWindow.start && dataWindow.requested_start < dataWindow.start) {
      clampText = ` Last run requested ${dataWindow.requested_start}, but the cache only begins ${dataWindow.start} — download older history (System → Market Data) to test earlier periods.`;
    }
    const survText = survivorship.warning ? ` ${survivorship.warning}` : "";
    note.textContent = `${windowText}${clampText}${survText}`;
  }
}

function renderStatusBar(overview) {
  const equity = document.getElementById("statusEquity");
  if (!equity) return;
  const metrics = overview.metrics || {};
  equity.textContent = metrics.final_equity != null ? formatCompactMoney(metrics.final_equity) : "-";
  document.getElementById("statusSharpe").textContent =
    metrics.sharpe != null ? formatNumber(metrics.sharpe) : "-";
  const drawdown = document.getElementById("statusMaxDD");
  drawdown.textContent = metrics.max_drawdown != null ? formatPct(metrics.max_drawdown) : "-";
  drawdown.classList.toggle("loss", Number(metrics.max_drawdown) < 0);
  document.getElementById("statusAsOf").textContent = overview.latest_signal_date || "-";
  const badge = document.getElementById("statusSurvivorship");
  const survivorship = overview.survivorship || {};
  if (survivorship.warning) {
    badge.hidden = false;
    badge.textContent = survivorship.point_in_time ? "PIT membership" : "Survivorship bias";
    badge.classList.toggle("info", Boolean(survivorship.point_in_time));
    badge.title = survivorship.warning;
    badge.onclick = () => activateTab("signal");
  } else {
    badge.hidden = true;
  }
}

function syncSignalWindowFromDownloadInputs() {
  document.getElementById("signalPriceStart").value = document.getElementById("dataStart").value || "";
  document.getElementById("signalPriceEnd").value = document.getElementById("dataEnd").value || "";
  document.getElementById("signalPriceTickers").value = document.getElementById("dataTickers").value.trim();
}

function syncSignalWindowFromOverview(dataWindow) {
  if (!dataWindow) return;
  const start = dataWindow.requested_start || dataWindow.start || "";
  const end = dataWindow.requested_end || dataWindow.end || "";
  document.getElementById("signalPriceStart").value = start || "";
  document.getElementById("signalPriceEnd").value = end || "";
  if ((dataWindow.requested_symbol_count || 0) > 0 && (dataWindow.requested_symbol_count || 0) <= 25) {
    document.getElementById("signalPriceTickers").value = (dataWindow.requested_symbols || []).join(", ");
  }
}

function renderMetrics(metrics) {
  const grid = document.getElementById("metricGrid");
  grid.innerHTML = "";
  metricSpecs.forEach(([label, key, type, tone]) => {
    const tile = document.createElement("article");
    tile.className = "metric";
    const valueClass = tone === "signed" ? signedClass(metrics[key]) : "";
    tile.innerHTML = `
      <div class="metric-label">${label}</div>
      <div class="metric-value ${valueClass}">${formatByType(metrics[key], type)}</div>
    `;
    grid.appendChild(tile);
  });
}

function renderHoldings(rows) {
  const body = document.getElementById("holdingsBody");
  body.innerHTML = "";
  const strategy = state.overview?.strategy || {};
  const lookback = strategy.lookback_days || 63;
  const winHeader = document.getElementById("candidateWinHeader");
  if (winHeader) {
    winHeader.textContent = `${lookback}D O/N Win`;
  }
  const meta = document.getElementById("bookMeta");
  if (meta) {
    const topN = strategy.top_n ? `top ${strategy.top_n}` : `${rows.length}`;
    const cap = strategy.max_weight ? `max ${formatPct(strategy.max_weight, 0)} each` : "capped weights";
    meta.textContent = `${rows.length} shown | ${topN} by ${lookback}D O/N Sharpe | ${cap}`;
  }
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${row.signal_date || ""}</td>
      <td>${row.exit_date || ""}</td>
      <td>${row.signal_rank ?? ""}</td>
      <td>${row.symbol}</td>
      <td>${row.name || ""}</td>
      <td>${row.sector || ""}</td>
      <td>${row.sector_code || ""}</td>
      <td>${formatCompactMoney(row.market_cap)}</td>
      <td>${formatPct(row.weight)}</td>
      <td>${formatNumber(row.overnight_sharpe)}</td>
      <td class="${signedClass(row.overnight_mean)}">${formatPct(row.overnight_mean)}</td>
      <td>${formatPct(row.overnight_vol)}</td>
      <td>${formatPct(row.overnight_win_rate)}</td>
      <td class="${signedClass(row.next_overnight_return)}">${formatPct(row.next_overnight_return)}</td>
    `;
    body.appendChild(tr);
  });
}

function renderPortfolios(rows) {
  const body = document.getElementById("portfolioBody");
  body.innerHTML = "";
  const meta = document.getElementById("portfolioSuiteMeta");
  if (meta) {
    const matrix = state.overview?.metrics?.portfolio_matrix || {};
    const dataWindow = state.overview?.data_window || {};
    const start = rows[0]?.start_date || matrix.start_date || dataWindow.start || "-";
    const end = rows[0]?.end_date || matrix.end_date || dataWindow.end || "-";
    const symbols = matrix.output_symbols || dataWindow.symbol_count;
    const observations = matrix.output_observations || rows[0]?.observations;
    const maxWeight = matrix.max_weight ?? matrix.effective_max_weight;
    const capText = maxWeight ? ` | cap ${formatPct(maxWeight)}` : "";
    const excluded = (matrix.excluded_symbols || []).length;
    const coverageText = dataWindow.start && start > dataWindow.start
      ? ` | starts ${start} (not ${dataWindow.start}) because every included symbol needs complete overlapping history — ${excluded} thin-history symbols excluded`
      : excluded
        ? ` | ${excluded} thin-history symbols excluded`
        : "";
    meta.textContent = rows.length
      ? `saved signal/data pipeline output | ${start} to ${end}${symbols ? ` | ${Number(symbols).toLocaleString()} symbols` : ""}${observations ? ` | ${Number(observations).toLocaleString()} obs` : ""}${capText}${coverageText}`
      : "Run Market Data or Signal Backtest to refresh this saved suite";
  }
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${row.portfolio}</td>
      ${renderPortfolioMetricCells(row)}
      <td>${row.positions ?? "-"}</td>
    `;
    body.appendChild(tr);
  });
}

function renderBuilder(result) {
  const summaryBody = document.getElementById("builderSummaryBody");
  const weightsAccordion = document.getElementById("builderWeightsAccordion");
  const meta = document.getElementById("builderMeta");
  const count = document.getElementById("builderWeightCount");
  summaryBody.innerHTML = "";
  weightsAccordion.innerHTML = "";

  if (!result) {
    meta.textContent = "";
    count.textContent = "";
    return;
  }

  const downloaded = result.downloaded_symbols && result.downloaded_symbols.length
    ? ` | fetched ${result.downloaded_symbols.join(", ")}`
    : "";
  const range = result.start_date && result.end_date ? ` | ${result.start_date} to ${result.end_date}` : "";
  const initial = result.initial_capital ? ` | initial ${formatMoney(result.initial_capital)}` : "";
  const costs = Number(result.fees_bps || 0) || Number(result.slippage_bps || 0)
    ? ` | costs ${formatNumber(Number(result.fees_bps || 0), 1)} fee bps + ${formatNumber(Number(result.slippage_bps || 0), 1)} slip bps`
    : "";
  const usedSymbols = result.symbols && result.symbols.length ? ` | used ${result.symbols.length} symbols` : "";
  const excluded = result.excluded_symbols && result.excluded_symbols.length
    ? ` | excluded ${result.excluded_symbols.length} thin-history symbols`
    : "";
  const rebalance = result.rebalance_frequency && result.rebalance_frequency !== "none"
    ? ` | ${result.rebalance_frequency} rebalance${result.rebalance_count ? `, ${Number(result.rebalance_count).toLocaleString()} snapshots` : ""}`
    : " | static weights";
  const estimationRows = result.effective_lookback_days || result.estimation_lookback_days;
  const historyMode = result.rebalance_frequency && result.rebalance_frequency !== "none"
    ? (result.history_mode === "lookback"
      ? `trailing ${Number(estimationRows || 0).toLocaleString()}-row estimation`
      : `expanding full-history estimation from prior rows`)
    : (result.history_mode === "lookback"
      ? `recent lookback ${result.lookback_days} rows`
      : `full history ${result.lookback_days} rows`);
  const performanceRows = result.performance_observations ? ` | ${Number(result.performance_observations).toLocaleString()} performance rows` : "";
  const dataStart = result.data_start ? ` | data since ${result.data_start}` : "";
  meta.textContent = `optimizer suite | ${result.return_model}${rebalance} | ${historyMode}${performanceRows}${range}${dataStart}${initial}${costs}${usedSymbols}${excluded}${downloaded}`;
  const weightLabel = result.rebalance_frequency && result.rebalance_frequency !== "none" ? "weight snapshots" : "positions";
  count.textContent = `${(result.summary || []).length.toLocaleString()} optimizers | ${(result.weights || []).length.toLocaleString()} ${weightLabel} | best Sharpe ${result.selected_portfolio}`;

  (result.summary || []).forEach((row) => {
    const tr = document.createElement("tr");
    const selected = row.portfolio === result.selected_portfolio ? " selected-row" : "";
    tr.className = selected;
    const badge = row.portfolio === result.selected_portfolio ? `<span class="inline-badge">Best Sharpe</span>` : "";
    tr.innerHTML = `
      <td><span class="portfolio-cell">${row.portfolio}${badge}</span></td>
      ${renderPortfolioMetricCells(row)}
      <td>${row.positions ?? "-"}</td>
    `;
    summaryBody.appendChild(tr);
  });

  const portfolioOrder = new Map((result.summary || []).map((row, index) => [row.portfolio, index]));
  const weightsByPortfolio = new Map();
  (result.weights || []).forEach((row) => {
    if (!weightsByPortfolio.has(row.portfolio)) weightsByPortfolio.set(row.portfolio, []);
    weightsByPortfolio.get(row.portfolio).push(row);
  });
  const summaryByPortfolio = new Map((result.summary || []).map((row) => [row.portfolio, row]));
  const portfolioNames = [...weightsByPortfolio.keys()].sort(
    (a, b) => (portfolioOrder.get(a) ?? 999) - (portfolioOrder.get(b) ?? 999) || a.localeCompare(b)
  );
  portfolioNames.forEach((portfolio) => {
    const allRows = weightsByPortfolio.get(portfolio);
    const rows = latestWeightRows(allRows)
      .slice()
      .sort((a, b) => Number(b.weight || 0) - Number(a.weight || 0) || String(a.symbol).localeCompare(String(b.symbol)));
    const summary = summaryByPortfolio.get(portfolio) || {};
    const details = document.createElement("details");
    details.className = "optimizer-group";
    if (portfolio === result.selected_portfolio) {
      details.open = true;
      details.classList.add("selected-optimizer");
    }
    const badge = portfolio === result.selected_portfolio ? `<span class="inline-badge">Best Sharpe</span>` : "";
    details.innerHTML = `
      <summary>
        <span class="optimizer-name">${portfolio}${badge}</span>
        <span class="optimizer-chips">
          <span>Cap ${formatPct(summary.max_weight_limit)}</span>
          <span>${formatPct(summary.weight_sum)} invested</span>
          <span>${formatPct(summary.cash_weight)} cash</span>
          <span>${rows.length.toLocaleString()} positions</span>
        </span>
      </summary>
      <div class="optimizer-detail-meta">${summary.optimizer_parameters || ""}${summary.last_rebalance_date ? ` | latest rebalance ${summary.last_rebalance_date}` : ""}${allRows.length !== rows.length ? ` | ${allRows.length.toLocaleString()} exported weight rows` : ""}</div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Weight</th>
              <th>Allocation</th>
            </tr>
          </thead>
          <tbody>
            ${rows.map((row) => `
              <tr>
                <td>${row.symbol}</td>
                <td>${formatPct(row.weight)}</td>
                <td>${formatMoneyFine(Number(row.weight || 0) * Number(result.initial_capital || 0))}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    `;
    details.querySelectorAll("th").forEach((header) => {
      const label = header.textContent.trim();
      attachHelpIconWithText(header, `optimizer-weight-header-${portfolio}-${label}`.replace(/\W+/g, "-").toLowerCase(), PORTFOLIO_HEADER_HELP[label]);
    });
    weightsAccordion.appendChild(details);
  });
}

function renderTradeMetrics(summary) {
  const grid = document.getElementById("tradeMetricGrid");
  if (!grid) return;
  grid.innerHTML = "";
  const metrics = summary || {};
  tradeMetricSpecs.forEach(([label, key, type, tone]) => {
    const tile = document.createElement("article");
    tile.className = "metric";
    const valueClass = tone === "signed" ? signedClass(metrics[key]) : "";
    tile.innerHTML = `
      <div class="metric-label">${label}</div>
      <div class="metric-value ${valueClass}">${formatByType(metrics[key], type)}</div>
    `;
    grid.appendChild(tile);
  });

  const meta = document.getElementById("tradeMeta");
  if (meta) {
    const sourceStart = metrics.source_start_date || "-";
    const sourceEnd = metrics.source_end_date || "-";
    const filteredStart = metrics.filtered_start_date || "-";
    const filteredEnd = metrics.filtered_end_date || "-";
    meta.textContent = `source ${sourceStart} to ${sourceEnd} | current range ${filteredStart} to ${filteredEnd}`;
  }
}

function tradeFilterValues() {
  return {
    symbol: (document.getElementById("tradeSymbolFilter")?.value || "").trim().toUpperCase(),
    start: document.getElementById("tradeStartFilter")?.value || "",
    end: document.getElementById("tradeEndFilter")?.value || "",
    pnl: document.getElementById("tradePnlFilter")?.value || "all",
    limit: Number(document.getElementById("tradeLimitFilter")?.value || 250),
  };
}

function tradeQueryParams(includeLimit = true) {
  const filters = tradeFilterValues();
  const params = new URLSearchParams();
  if (includeLimit) params.set("limit", String(Math.max(1, filters.limit)));
  if (filters.symbol) params.set("symbol", filters.symbol);
  if (filters.start) params.set("start", filters.start);
  if (filters.end) params.set("end", filters.end);
  if (filters.pnl && filters.pnl !== "all") params.set("pnl", filters.pnl);
  return params;
}

function syncTradeDateDefaults(summary) {
  const startInput = document.getElementById("tradeStartFilter");
  const endInput = document.getElementById("tradeEndFilter");
  if (startInput && !startInput.value && summary?.source_start_date) {
    startInput.value = summary.source_start_date;
  }
  if (endInput && !endInput.value && summary?.source_end_date) {
    endInput.value = summary.source_end_date;
  }
}

function renderTrades(rows = state.trades) {
  const body = document.getElementById("tradesBody");
  body.innerHTML = "";
  renderTradeMetrics(state.tradeSummary);
  const rendered = rows.slice().reverse();
  const summary = state.tradeSummary || {};
  const sourceTotal = Number(summary.source_total_trades || summary.total_trades || 0);
  const filteredTotal = Number(summary.filtered_trades || 0);
  const returned = Number(summary.returned_trades || rows.length || 0);
  const latestExit = summary.latest_exit_date;
  document.getElementById("tradeCount").textContent = `${rendered.length.toLocaleString()} rendered | ${filteredTotal.toLocaleString()} filtered | ${sourceTotal.toLocaleString()} source${latestExit ? ` | latest exit ${latestExit}` : ""}`;
  const context = document.getElementById("tradeContext");
  if (context) {
    const sourceStart = summary.source_start_date || "-";
    const sourceEnd = summary.source_end_date || "-";
    const filterStart = summary.filtered_start_date || "-";
    const filterEnd = summary.filtered_end_date || "-";
    context.textContent = `Source data ${sourceStart} to ${sourceEnd}. Current filter range ${filterStart} to ${filterEnd}. Table contains latest ${returned.toLocaleString()} rows from the filtered set; CSV exports all ${filteredTotal.toLocaleString()} filtered rows.`;
  }
  if (!rendered.length) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td colspan="11">No trades match the current filters.</td>`;
    body.appendChild(tr);
    return;
  }
  rendered.forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${row.signal_date}</td>
      <td>${row.exit_date}</td>
      <td>${row.signal_rank ?? ""}</td>
      <td>${row.symbol}</td>
      <td>${formatPct(row.weight)}</td>
      <td class="${signedClass(row.overnight_return)}">${formatPct(row.overnight_return)}</td>
      <td>${formatMoneyFine(row.notional)}</td>
      <td class="${signedClass(row.gross_pnl)}">${formatMoneyFine(row.gross_pnl)}</td>
      <td class="loss">${formatMoneyFine(row.cost)}</td>
      <td class="${signedClass(row.net_pnl)}">${formatMoneyFine(row.net_pnl)}</td>
      <td>${formatNumber(row.overnight_sharpe)}</td>
    `;
    body.appendChild(tr);
  });
}

function getCanvasContext(canvasId) {
  const canvas = document.getElementById(canvasId);
  const ratio = window.devicePixelRatio || 1;
  const width = canvas.clientWidth;
  if (!canvas.dataset.logicalHeight) {
    canvas.dataset.logicalHeight = String(canvas.height || 320);
  }
  const height = Number(canvas.dataset.logicalHeight);
  canvas.style.height = `${height}px`;
  canvas.width = Math.floor(width * ratio);
  canvas.height = Math.floor(height * ratio);
  const context = canvas.getContext("2d");
  context.scale(ratio, ratio);
  return { canvas, context, width, height };
}

function yForValue(value, min, max, area) {
  const span = max - min || 1;
  return area.top + area.height - ((value - min) / span) * area.height;
}

function xForIndex(index, rows, area) {
  return area.left + (area.width * index) / Math.max(rows.length - 1, 1);
}

function dateValue(row) {
  const parsed = new Date(`${row?.date}T00:00:00`);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function curveRangeDays() {
  return {
    "1y": 365,
    "3y": 365 * 3,
    "5y": 365 * 5,
    "10y": 365 * 10,
  }[state.curves.range] || null;
}

function visibleCurveRows() {
  if (!state.equity.length) return [];
  const days = curveRangeDays();
  if (!days) return state.equity;
  const latest = dateValue(state.equity[state.equity.length - 1]);
  if (!latest) return state.equity;
  const cutoff = new Date(latest);
  cutoff.setDate(cutoff.getDate() - days);
  return state.equity.filter((row) => {
    const date = dateValue(row);
    return date && date >= cutoff;
  });
}

function expandBounds(values, floor = null, ceiling = null) {
  let min = Math.min(...values);
  let max = Math.max(...values);
  if (floor !== null) min = Math.min(min, floor);
  if (ceiling !== null) max = Math.max(max, ceiling);
  const span = max - min || Math.max(Math.abs(max), 1);
  const pad = span * 0.06;
  return {
    min: floor === 0 ? 0 : min - pad,
    max: ceiling === 0 ? 0 : max + pad,
  };
}

function drawEmptyChart(context, width, height, title) {
  const colors = chartColors();
  context.clearRect(0, 0, width, height);
  context.fillStyle = colors.text;
  context.font = `700 13px ${CHART_FONT}`;
  context.textAlign = "center";
  context.fillText(title, width / 2, 24);
  context.fillStyle = colors.muted;
  context.font = `12px ${CHART_FONT}`;
  context.fillText("No data available", width / 2, height / 2);
}

function tickIndexes(rows, width) {
  const count = width > 1000 ? 7 : width > 720 ? 5 : 3;
  const maxIndex = Math.max(rows.length - 1, 0);
  return [...new Set(Array.from({ length: count }, (_, i) => Math.round((maxIndex * i) / Math.max(count - 1, 1))))];
}

function drawChartAxes(context, rows, bounds) {
  const { width, height, title, xLabel, yLabel, min, max, formatY } = bounds;
  const padding = { top: 44, right: 26, bottom: 60, left: 86 };
  const area = {
    left: padding.left,
    top: padding.top,
    width: width - padding.left - padding.right,
    height: height - padding.top - padding.bottom,
  };
  const axisY = area.top + area.height;
  const colors = chartColors();

  context.fillStyle = colors.chartBg;
  context.fillRect(area.left, area.top, area.width, area.height);

  context.fillStyle = colors.text;
  context.font = `700 13px ${CHART_FONT}`;
  context.textAlign = "center";
  context.fillText(title, area.left + area.width / 2, 24);

  for (let i = 0; i <= 4; i += 1) {
    const value = max - ((max - min) * i) / 4;
    const y = yForValue(value, min, max, area);
    context.strokeStyle = i === 4 ? colors.gridStrong : colors.grid;
    context.lineWidth = 1;
    context.beginPath();
    context.moveTo(area.left, y);
    context.lineTo(area.left + area.width, y);
    context.stroke();

    context.fillStyle = colors.muted;
    context.font = `11px ${CHART_MONO}`;
    context.textAlign = "right";
    context.fillText(formatY(value), area.left - 10, y + 4);
  }

  context.strokeStyle = colors.gridStrong;
  context.beginPath();
  context.moveTo(area.left, area.top);
  context.lineTo(area.left, axisY);
  context.lineTo(area.left + area.width, axisY);
  context.stroke();

  tickIndexes(rows, width).forEach((index) => {
    const x = xForIndex(index, rows, area);
    context.strokeStyle = colors.gridStrong;
    context.beginPath();
    context.moveTo(x, axisY);
    context.lineTo(x, axisY + 5);
    context.stroke();

    context.fillStyle = colors.muted;
    context.font = `11px ${CHART_MONO}`;
    context.textAlign = index === 0 ? "left" : index === rows.length - 1 ? "right" : "center";
    context.fillText(formatShortDate(rows[index]?.date), x, axisY + 20);
  });

  context.fillStyle = colors.muted;
  context.font = `12px ${CHART_FONT}`;
  context.textAlign = "center";
  context.fillText(xLabel, area.left + area.width / 2, height - 11);

  context.save();
  context.translate(18, area.top + area.height / 2);
  context.rotate(-Math.PI / 2);
  context.fillText(yLabel, 0, 0);
  context.restore();

  return area;
}

function drawHover(context, rows, index, area, min, max, valueKey, color, formatY) {
  if (!Number.isInteger(index) || index < 0 || index >= rows.length) return;
  const value = Number(rows[index][valueKey]);
  if (!Number.isFinite(value)) return;
  const x = xForIndex(index, rows, area);
  const y = yForValue(value, min, max, area);
  const colors = chartColors();

  context.save();
  context.setLineDash([4, 4]);
  context.strokeStyle = colors.muted;
  context.lineWidth = 1;
  context.beginPath();
  context.moveTo(x, area.top);
  context.lineTo(x, area.top + area.height);
  context.stroke();
  context.restore();

  context.fillStyle = colors.chartBg;
  context.strokeStyle = color;
  context.lineWidth = 2;
  context.shadowColor = color;
  context.shadowBlur = 10;
  context.beginPath();
  context.arc(x, y, 4.5, 0, Math.PI * 2);
  context.fill();
  context.stroke();
  context.shadowBlur = 0;

  const label = formatY(value);
  context.font = `600 11px ${CHART_MONO}`;
  const labelWidth = Math.max(58, context.measureText(label).width + 16);
  const labelX = Math.min(Math.max(x - labelWidth / 2, area.left + 4), area.left + area.width - labelWidth - 4);
  const labelY = Math.max(area.top + 8, y - 30);
  context.fillStyle = color;
  context.beginPath();
  if (context.roundRect) {
    context.roundRect(labelX, labelY, labelWidth, 22, 6);
    context.fill();
  } else {
    context.fillRect(labelX, labelY, labelWidth, 22);
  }
  context.fillStyle = "#ffffff";
  context.textAlign = "center";
  context.fillText(label, labelX + labelWidth / 2, labelY + 15);
}

function drawEquityChart(rows) {
  const { context, width, height } = getCanvasContext("equityChart");
  context.clearRect(0, 0, width, height);
  if (!rows.length) {
    drawEmptyChart(context, width, height, "Equity Curve");
    return;
  }

  const values = rows.map((row) => Number(row.equity)).filter(Number.isFinite);
  if (!values.length) {
    drawEmptyChart(context, width, height, "Equity Curve");
    return;
  }
  const { min, max } = expandBounds(values);
  const area = drawChartAxes(context, rows, {
    width,
    height,
    title: "Strategy Equity Curve",
    xLabel: "Exit date",
    yLabel: "Portfolio equity",
    min,
    max,
    formatY: formatAxisMoney,
  });

  const colors = chartColors();
  const gradient = context.createLinearGradient(0, area.top, 0, area.top + area.height);
  gradient.addColorStop(0, colors.accentSoftTop);
  gradient.addColorStop(1, colors.accentSoftBottom);

  context.beginPath();
  let started = false;
  rows.forEach((row, index) => {
    const value = Number(row.equity);
    if (!Number.isFinite(value)) return;
    const x = xForIndex(index, rows, area);
    const y = yForValue(value, min, max, area);
    if (!started) {
      context.moveTo(x, y);
      started = true;
    } else {
      context.lineTo(x, y);
    }
  });
  context.lineTo(area.left + area.width, area.top + area.height);
  context.lineTo(area.left, area.top + area.height);
  context.closePath();
  context.fillStyle = gradient;
  context.fill();

  context.strokeStyle = colors.accent;
  context.lineWidth = 2.4;
  context.shadowColor = colors.accent;
  context.shadowBlur = 12;
  context.beginPath();
  started = false;
  rows.forEach((row, index) => {
    const value = Number(row.equity);
    if (!Number.isFinite(value)) return;
    const x = xForIndex(index, rows, area);
    const y = yForValue(value, min, max, area);
    if (!started) {
      context.moveTo(x, y);
      started = true;
    } else {
      context.lineTo(x, y);
    }
  });
  context.stroke();
  context.shadowBlur = 0;
  drawHover(context, rows, state.curves.hoverIndex, area, min, max, "equity", colors.accent, formatAxisMoney);
}

function drawDrawdownChart(rows) {
  const { context, width, height } = getCanvasContext("drawdownChart");
  context.clearRect(0, 0, width, height);
  if (!rows.length) {
    drawEmptyChart(context, width, height, "Drawdown Curve");
    return;
  }

  const values = rows.map((row) => Number(row.drawdown)).filter(Number.isFinite);
  if (!values.length) {
    drawEmptyChart(context, width, height, "Drawdown Curve");
    return;
  }
  const { min, max } = expandBounds(values, null, 0);
  const area = drawChartAxes(context, rows, {
    width,
    height,
    title: "Strategy Drawdown Curve",
    xLabel: "Exit date",
    yLabel: "Drawdown",
    min,
    max,
    formatY: (value) => formatPct(value, 1),
  });
  const zeroY = yForValue(0, min, max, area);
  const colors = chartColors();

  context.fillStyle = colors.lossSoft;
  rows.forEach((row, index) => {
    const value = Number(row.drawdown) || 0;
    const x = xForIndex(index, rows, area);
    const y = yForValue(value, min, max, area);
    const nextX = index < rows.length - 1 ? xForIndex(index + 1, rows, area) : x;
    context.fillRect(x, zeroY, Math.max(1, nextX - x), Math.max(1, y - zeroY));
  });

  context.strokeStyle = colors.loss;
  context.lineWidth = 2;
  context.beginPath();
  let started = false;
  rows.forEach((row, index) => {
    const value = Number(row.drawdown) || 0;
    const x = xForIndex(index, rows, area);
    const y = yForValue(value, min, max, area);
    if (!started) {
      context.moveTo(x, y);
      started = true;
    } else {
      context.lineTo(x, y);
    }
  });
  context.stroke();
  drawHover(context, rows, state.curves.hoverIndex, area, min, max, "drawdown", colors.loss, (value) => formatPct(value, 2));
}

function updateCurveReadout(rows) {
  const node = document.getElementById("curveReadout");
  if (!node) return;
  const index = Number.isInteger(state.curves.hoverIndex) ? state.curves.hoverIndex : rows.length - 1;
  const row = rows[index];
  const labels = row
    ? [`Date ${row.date}`, `Equity ${formatMoney(row.equity)}`, `Drawdown ${formatPct(row.drawdown)}`]
    : ["Date -", "Equity -", "Drawdown -"];
  node.replaceChildren(...labels.map((label) => {
    const span = document.createElement("span");
    span.textContent = label;
    return span;
  }));
}

function updateRangeButtons() {
  document.querySelectorAll(".curve-toolbar [data-range]").forEach((button) => {
    button.classList.toggle("active", button.dataset.range === state.curves.range);
  });
}

function renderCurves() {
  const rows = visibleCurveRows();
  if (state.curves.hoverIndex !== null && state.curves.hoverIndex >= rows.length) {
    state.curves.hoverIndex = rows.length ? rows.length - 1 : null;
  }
  const rangeNode = document.getElementById("equityRange");
  if (rangeNode) {
    const rangeLabel = state.curves.range === "full" ? "Full" : state.curves.range.toUpperCase();
    rangeNode.textContent = rows.length
      ? `${rangeLabel}: ${rows[0].date} to ${rows[rows.length - 1].date} (${rows.length.toLocaleString()} observations)`
      : "";
  }
  updateCurveReadout(rows);
  updateRangeButtons();
  drawEquityChart(rows);
  drawDrawdownChart(rows);
}

function handleCurvePointerMove(event) {
  const rows = visibleCurveRows();
  if (!rows.length) return;
  const canvas = event.currentTarget;
  const rect = canvas.getBoundingClientRect();
  const left = 86;
  const right = 26;
  const chartWidth = Math.max(rect.width - left - right, 1);
  const rawIndex = Math.round(((event.clientX - rect.left - left) / chartWidth) * (rows.length - 1));
  state.curves.hoverIndex = Math.min(Math.max(rawIndex, 0), rows.length - 1);
  renderCurves();
}

function handleCurvePointerLeave() {
  state.curves.hoverIndex = null;
  renderCurves();
}

async function loadDashboard() {
  const [overview, equity, daily, trades] = await Promise.all([
    fetchJson("/api/overview"),
    fetchJson("/api/equity"),
    fetchJson("/api/daily"),
    fetchJson(`/api/trades?${tradeQueryParams(true).toString()}`),
  ]);

  state.overview = overview;
  state.equity = equity.rows || [];
  state.daily = daily.rows || [];
  state.trades = trades.rows || [];
  state.tradeSummary = trades.summary || null;
  syncTradeDateDefaults(state.tradeSummary);
  const strategy = overview.strategy || {};
  const backtest = overview.backtest || {};
  syncBacktestControls({
    ...strategy,
    initial_capital: backtest.initial_capital,
    fees_bps: backtest.fees_bps,
    slippage_bps: backtest.slippage_bps,
    cost_model: backtest.cost_model,
    capital_capacity: backtest.capital_capacity,
    cash_rate: backtest.cash_rate,
    max_adv_participation: backtest.max_adv_participation,
  });
  renderSurvivorship(overview.survivorship);
  renderStatusBar(overview);
  renderOverviewHome(overview);
  syncSignalWindowFromOverview(overview.data_window);

  document.getElementById("asOf").textContent = overview.latest_signal_date
    ? `Current book date ${overview.latest_signal_date} | ${strategy.lookback_days || 63}D signal lookback`
    : "No current book";
  const summaryMeta = document.getElementById("summaryMeta");
  if (summaryMeta) {
    const start = state.equity[0]?.date;
    const end = state.equity[state.equity.length - 1]?.date;
    const dataWindow = overview.data_window || {};
    const symbolText = dataWindow.symbol_count ? `${dataWindow.symbol_count.toLocaleString()} symbols` : "selected symbols";
    const windowText = dataWindow.start && dataWindow.end
      ? `price window ${dataWindow.start} to ${dataWindow.end} | ${symbolText}`
      : "selected signal backtest price window";
    const clampNotes = [];
    if (dataWindow.requested_start && dataWindow.start && dataWindow.requested_start < dataWindow.start) {
      clampNotes.push(`requested ${dataWindow.requested_start} but cache begins ${dataWindow.start}`);
    }
    if (dataWindow.requested_end && dataWindow.end && dataWindow.requested_end > dataWindow.end) {
      clampNotes.push(`requested end ${dataWindow.requested_end} but cache ends ${dataWindow.end}`);
    }
    const clampText = clampNotes.length ? ` | ${clampNotes.join("; ")}` : "";
    summaryMeta.textContent = start && end
      ? `${start} to ${end} | ${windowText}${clampText} | not the chart zoom window`
      : `${windowText}${clampText} | not the chart zoom window`;
  }

  renderMetrics(overview.metrics || {});
  renderHoldings(overview.latest_holdings || []);
  renderPortfolios(overview.portfolio_summary || []);
  renderTrades();
  renderCurves();
}

async function loadTradesFromFilters() {
  const result = await fetchJson(`/api/trades?${tradeQueryParams(true).toString()}`);
  state.trades = result.rows || [];
  state.tradeSummary = result.summary || null;
  renderTrades();
}

function renderUniverseSelector(rows) {
  const select = document.getElementById("universeSelect");
  select.innerHTML = "";
  const bySector = new Map();
  rows.forEach((row) => {
    const sectorCode = row.sector_code || "OTHER";
    const sector = row.sector || "Unclassified";
    const key = `${sectorCode} - ${sector}`;
    if (!bySector.has(key)) bySector.set(key, []);
    bySector.get(key).push(row);
  });

  [...bySector.keys()].sort().forEach((label) => {
    const group = document.createElement("optgroup");
    group.label = label;
    bySector.get(label)
      .sort((a, b) => (Number(b.market_cap) || 0) - (Number(a.market_cap) || 0) || a.symbol.localeCompare(b.symbol))
      .forEach((row) => {
        const option = document.createElement("option");
        option.value = row.symbol;
        const cap = formatCompactMoney(row.market_cap);
        const cacheMark = row.in_price_cache ? " cached" : "";
        option.textContent = `${row.symbol} - ${row.name || row.symbol}${cap ? ` (${cap})` : ""}${cacheMark}`;
        group.appendChild(option);
      });
    select.appendChild(group);
  });
}

async function loadUniverse(refreshMarketCaps = false) {
  const result = await fetchJson(`/api/universe?refresh_market_caps=${refreshMarketCaps ? "true" : "false"}`);
  state.universe = result.rows || [];
  renderUniverseSelector(state.universe);
}

async function rerun(event) {
  if (event) event.preventDefault();
  const button = document.getElementById("runButton");
  const status = document.getElementById("backtestStatus");
  button.disabled = true;
  status.textContent = "Running";
  startTaskProgress("taskProgress", "Running signal backtest...");
  try {
    const result = await fetchJson("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(backtestPayload()),
    });
    await loadDashboard();
    status.textContent = `${result.trades.toLocaleString()} trades`;
    finishTaskProgress("taskProgress", "Backtest complete");
    toast("Signal backtest complete");
  } catch (error) {
    status.textContent = "Failed";
    finishTaskProgress("taskProgress", "Backtest failed", true);
    toast(`Backtest failed: ${error.message}`);
  } finally {
    button.disabled = false;
  }
}

async function downloadRealData(event) {
  event.preventDefault();
  const button = document.getElementById("downloadButton");
  const status = document.getElementById("dataStatus");
  button.disabled = true;
  status.textContent = "Downloading";
  startTaskProgress("taskProgress", "Downloading market data...");
  try {
    const limitValue = document.getElementById("dataLimit").value;
    const tickersValue = document.getElementById("dataTickers").value.trim();
    const payload = {
      source: document.getElementById("dataSource").value,
      tickers: tickersValue || null,
      start: document.getElementById("dataStart").value || "2018-01-01",
      end: document.getElementById("dataEnd").value || null,
      symbols_limit: tickersValue ? null : (limitValue ? Number(limitValue) : null),
      run_backtest: document.getElementById("runAfterDownload").checked,
      incremental: document.getElementById("incrementalDownload").checked,
      strategy: document.getElementById("runAfterDownload").checked ? backtestPayload() : null,
    };
    if (payload.run_backtest) {
      payload.strategy.price_start = payload.start;
      payload.strategy.price_end = payload.end;
      payload.strategy.price_symbols = tickersValue || null;
    }
    const result = await fetchJson("/api/data/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const missing = result.missing_symbols && result.missing_symbols.length ? `, ${result.missing_symbols.length} missing` : "";
    status.textContent = `${result.returned_symbols.length} updated${missing}`;
    await loadDashboard();
    await loadUniverse(false);
    finishTaskProgress("taskProgress", "Market data updated");
    toast(`Price cache has ${result.rows.toLocaleString()} rows`);
  } catch (error) {
    status.textContent = "Failed";
    finishTaskProgress("taskProgress", "Download failed", true);
    toast(`Download failed: ${error.message}`);
  } finally {
    button.disabled = false;
  }
}

async function buildPortfolio(event) {
  if (event) event.preventDefault();
  const button = document.getElementById("buildPortfolioButton");
  const status = document.getElementById("builderStatus");
  button.disabled = true;
  status.textContent = "Building";
  startTaskProgress("taskProgress", "Building portfolio...");
  try {
    const useAllHistory = builderUsesFullHistory();
    const lookbackValue = document.getElementById("lookbackDays").value;
    const payload = {
      symbols: document.getElementById("portfolioTickers").value,
      use_entire_universe: document.getElementById("universeMode").value === "all",
      method: "best",
      return_model: document.getElementById("returnModel").value,
      rebalance_frequency: document.getElementById("rebalanceFrequency").value,
      initial_capital: numberInputValue("builderInitialEquity", 1000000),
      fees_bps: numberInputValue("builderFeesBps", 0),
      slippage_bps: numberInputValue("builderSlippageBps", 0),
      max_weight: numberInputValue("maxWeight", 0.12),
      kelly_fraction: numberInputValue("kellyFraction", 0.5),
      kelly_max_weight: optionalNumberInputValue("kellyMaxWeight"),
      mean_variance_risk_aversion: numberInputValue("meanVarianceRiskAversion", 8),
      mean_variance_max_weight: optionalNumberInputValue("meanVarianceMaxWeight"),
      minimum_variance_max_weight: optionalNumberInputValue("minimumVarianceMaxWeight"),
      inverse_volatility_max_weight: optionalNumberInputValue("inverseVolatilityMaxWeight"),
      cvar_alpha: numberInputValue("cvarAlpha", 0.95),
      cvar_max_weight: optionalNumberInputValue("cvarMaxWeight"),
      black_litterman_tau: numberInputValue("blackLittermanTau", 0.05),
      black_litterman_prior_risk_aversion: numberInputValue("blackLittermanPriorRiskAversion", 2.5),
      black_litterman_risk_aversion: numberInputValue("blackLittermanRiskAversion", 8),
      black_litterman_max_weight: optionalNumberInputValue("blackLittermanMaxWeight"),
      lookback_days: useAllHistory ? null : Number(lookbackValue || 756),
      auto_download_missing: document.getElementById("autoDownloadMissing").checked,
      refresh_history: document.getElementById("refreshHistory").checked,
      data_start: document.getElementById("builderDataStart").value || "2018-01-01",
      data_source: document.getElementById("builderDataSource").value,
    };
    const result = await fetchJson("/api/portfolio/build", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (payload.rebalance_frequency !== "none" && result.rebalance_frequency !== payload.rebalance_frequency) {
      throw new Error(
        "The backend did not run the requested rebalancing mode. Restart NightFall Alpha with start_nightfall_alpha.bat, then rebuild the portfolio."
      );
    }
    state.builder = result;
    renderBuilder(result);
    status.textContent = `Suite built | Best Sharpe: ${result.selected_portfolio}`;
    finishTaskProgress("taskProgress", "Portfolio built");
    toast("Portfolio built");
  } catch (error) {
    status.textContent = "Failed";
    finishTaskProgress("taskProgress", "Builder failed", true);
    toast(`Builder failed: ${error.message}`);
  } finally {
    button.disabled = false;
  }
}

function downloadBuilderSummaryCsv() {
  const result = state.builder;
  if (!result || !(result.summary || []).length) {
    toast("Build a portfolio first");
    return;
  }
  const rows = (result.summary || []).map((row) => ({
    ...row,
    selected: row.portfolio === result.selected_portfolio,
    return_model: result.return_model,
    rebalance_frequency: result.rebalance_frequency || "none",
    builder_start_date: result.start_date,
    builder_end_date: result.end_date,
    builder_rows: result.lookback_days,
    estimation_lookback_days: result.estimation_lookback_days,
    performance_observations: result.performance_observations,
    builder_symbol_count: (result.symbols || []).length,
    fees_bps: result.fees_bps,
    slippage_bps: result.slippage_bps,
  }));
  const columns = [
    { label: "selected", value: "selected" },
    { label: "portfolio", value: "portfolio" },
    { label: "return_model", value: "return_model" },
    { label: "rebalance_frequency", value: "rebalance_frequency" },
    { label: "builder_start_date", value: "builder_start_date" },
    { label: "builder_end_date", value: "builder_end_date" },
    { label: "builder_rows", value: "builder_rows" },
    { label: "estimation_lookback_days", value: "estimation_lookback_days" },
    { label: "performance_observations", value: "performance_observations" },
    { label: "builder_symbol_count", value: "builder_symbol_count" },
    { label: "fees_bps", value: "fees_bps" },
    { label: "slippage_bps", value: "slippage_bps" },
    { label: "optimizer_parameters", value: "optimizer_parameters" },
    ...portfolioMetricSpecs.map(([, key]) => ({ label: key, value: key })),
    { label: "positions", value: "positions" },
  ];
  downloadTextFile("nightfall_alpha_portfolio_metrics.csv", rowsToCsv(rows, columns));
  toast("Portfolio metrics CSV downloaded");
}

function downloadBuilderWeightsCsv() {
  const result = state.builder;
  if (!result || !(result.weights || []).length) {
    toast("Build a portfolio first");
    return;
  }
  const summaryByPortfolio = new Map((result.summary || []).map((row) => [row.portfolio, row]));
  const rows = (result.weights || []).map((row) => {
    const summary = summaryByPortfolio.get(row.portfolio) || {};
    return {
      selected: row.portfolio === result.selected_portfolio,
      portfolio: row.portfolio,
      rebalance_date: row.rebalance_date || "",
      symbol: row.symbol,
      weight: row.weight,
      allocation: Number(row.weight || 0) * Number(result.initial_capital || 0),
      return_model: result.return_model,
      rebalance_frequency: result.rebalance_frequency || "none",
      start_date: result.start_date,
      end_date: result.end_date,
      observations: summary.observations,
      initial_capital: result.initial_capital,
      fees_bps: result.fees_bps,
      slippage_bps: result.slippage_bps,
      portfolio_final_equity: summary.final_equity,
      portfolio_total_return: summary.total_return,
      portfolio_sharpe: summary.sharpe,
      portfolio_sortino: summary.sortino,
      portfolio_calmar: summary.calmar,
      portfolio_cap: summary.max_weight_limit,
      portfolio_parameters: summary.optimizer_parameters,
      portfolio_invested: summary.weight_sum,
      portfolio_cash: summary.cash_weight,
    };
  });
  const columns = [
    { label: "selected", value: "selected" },
    { label: "portfolio", value: "portfolio" },
    { label: "rebalance_date", value: "rebalance_date" },
    { label: "symbol", value: "symbol" },
    { label: "weight", value: "weight" },
    { label: "allocation", value: "allocation" },
    { label: "return_model", value: "return_model" },
    { label: "rebalance_frequency", value: "rebalance_frequency" },
    { label: "start_date", value: "start_date" },
    { label: "end_date", value: "end_date" },
    { label: "observations", value: "observations" },
    { label: "initial_capital", value: "initial_capital" },
    { label: "fees_bps", value: "fees_bps" },
    { label: "slippage_bps", value: "slippage_bps" },
    { label: "portfolio_final_equity", value: "portfolio_final_equity" },
    { label: "portfolio_total_return", value: "portfolio_total_return" },
    { label: "portfolio_sharpe", value: "portfolio_sharpe" },
    { label: "portfolio_sortino", value: "portfolio_sortino" },
    { label: "portfolio_calmar", value: "portfolio_calmar" },
    { label: "portfolio_cap", value: "portfolio_cap" },
    { label: "portfolio_parameters", value: "portfolio_parameters" },
    { label: "portfolio_invested", value: "portfolio_invested" },
    { label: "portfolio_cash", value: "portfolio_cash" },
  ];
  downloadTextFile("nightfall_alpha_portfolio_executions.csv", rowsToCsv(rows, columns));
  toast("Portfolio executions CSV downloaded");
}

function downloadTradesCsv() {
  const query = tradeQueryParams(false);
  const suffix = query.toString();
  openDownloadUrl(`/api/trades.csv${suffix ? `?${suffix}` : ""}`);
  toast("Trade blotter CSV download started");
}

function addUniverseSelection() {
  const select = document.getElementById("universeSelect");
  const selected = [...select.selectedOptions].map((option) => option.value);
  if (!selected.length) return;
  const input = document.getElementById("portfolioTickers");
  const existing = input.value
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
  const merged = [...new Set([...existing, ...selected])];
  input.value = merged.join(", ");
  document.getElementById("universeMode").value = "selected";
}

function syncUniverseMode() {
  const useAll = document.getElementById("universeMode").value === "all";
  document.getElementById("portfolioTickers").disabled = useAll;
  document.getElementById("universeSelect").disabled = useAll;
  document.getElementById("addUniverseButton").disabled = useAll;
}

function syncDataSourceStart() {
  const source = document.getElementById("dataSource").value;
  const start = document.getElementById("dataStart");
  if ((source === "stooq" || source === "yahoo_max") && start.value === "2018-01-01") {
    start.value = "1990-01-01";
  }
  if (source === "yahoo_max") {
    start.value = "1900-01-01";
  }
}

function syncBuilderDataSourceStart() {
  const source = document.getElementById("builderDataSource").value;
  const start = document.getElementById("builderDataStart");
  if (source === "yahoo_max") {
    start.value = "1900-01-01";
  } else if (source === "stooq") {
    if (start.value === "2018-01-01" || start.value === "1900-01-01") start.value = "1990-01-01";
  }
  syncBuilderHistoryControls();
}

function syncBuilderHistoryControls() {
  const useAllHistory = document.getElementById("useAllHistory");
  const lookback = document.getElementById("lookbackDays");
  useAllHistory.disabled = false;
  lookback.disabled = builderUsesFullHistory();
  lookback.title = lookback.disabled
    ? "Use All History is active, so the numeric lookback is ignored."
    : "Recent estimation-window rows used by Portfolio Research.";
}

function syncLookbackMode() {
  syncBuilderHistoryControls();
}

const SERIES_PALETTE = ["#22d3ee", "#a78bfa", "#f59e0b", "#34d399", "#fb7185", "#f472b6"];

// ===================== INTERACTIVE CHARTS (ECharts) =====================
// Registry keeps the last payload per chart so theme switches and tab
// visibility changes can re-render without refetching.
const interactiveCharts = new Map();

function chartThemeColors() {
  const styles = getComputedStyle(document.documentElement);
  return {
    text: styles.getPropertyValue("--text").trim() || "#e9eef8",
    muted: styles.getPropertyValue("--muted").trim() || "#8a94ac",
    border: styles.getPropertyValue("--glass-border").trim() || "rgba(255,255,255,0.09)",
  };
}

function renderInteractiveChart(elementId, rows, columns, options = {}) {
  const el = document.getElementById(elementId);
  if (!el || typeof echarts === "undefined") return;
  let entry = interactiveCharts.get(elementId);
  if (!entry) {
    entry = { chart: echarts.init(el, null, { renderer: "canvas" }), rows: [], columns: [], options: {} };
    interactiveCharts.set(elementId, entry);
  }
  entry.rows = rows;
  entry.columns = columns;
  entry.options = options;

  const colors = chartThemeColors();
  const palette = columns.map((_, index) => SERIES_PALETTE[index % SERIES_PALETTE.length]);
  const yFormatter = options.yFormatter || ((value) => formatNumber(value, 2));

  if (!rows.length || !columns.length) {
    entry.chart.setOption({
      backgroundColor: "transparent",
      title: {
        text: options.emptyText || "Run to load data",
        left: "center",
        top: "center",
        textStyle: { color: colors.muted, fontSize: 13, fontWeight: 500 },
      },
      xAxis: { show: false },
      yAxis: { show: false },
      series: [],
    }, true);
    return;
  }

  entry.chart.setOption({
    backgroundColor: "transparent",
    color: palette,
    animationDuration: 400,
    grid: { left: 64, right: 24, top: 44, bottom: 66 },
    legend: {
      top: 4,
      icon: "roundRect",
      itemWidth: 14,
      itemHeight: 4,
      textStyle: { color: colors.muted, fontSize: 12 },
      inactiveColor: colors.border,
    },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "line", lineStyle: { color: colors.muted } },
      backgroundColor: "rgba(10, 14, 26, 0.92)",
      borderColor: colors.border,
      textStyle: { color: "#e9eef8", fontSize: 12 },
      valueFormatter: (value) => (value === null || value === undefined ? "-" : yFormatter(value)),
    },
    xAxis: {
      type: "category",
      data: rows.map((row) => row.date),
      axisLabel: { color: colors.muted, fontSize: 11 },
      axisLine: { lineStyle: { color: colors.border } },
      axisTick: { show: false },
    },
    yAxis: {
      type: "value",
      scale: true,
      axisLabel: { color: colors.muted, fontSize: 11, formatter: yFormatter },
      splitLine: { lineStyle: { color: colors.border } },
    },
    dataZoom: [
      { type: "inside", throttle: 50 },
      {
        type: "slider",
        height: 20,
        bottom: 10,
        borderColor: colors.border,
        backgroundColor: "transparent",
        fillerColor: "rgba(99, 102, 241, 0.18)",
        handleStyle: { color: colors.muted },
        moveHandleStyle: { color: colors.muted },
        textStyle: { color: colors.muted, fontSize: 10 },
        dataBackground: { lineStyle: { color: colors.border }, areaStyle: { color: "transparent" } },
      },
    ],
    series: columns.map((column) => ({
      name: column,
      type: "line",
      showSymbol: false,
      lineStyle: { width: 2 },
      emphasis: { focus: "series" },
      connectNulls: false,
      data: rows.map((row) => {
        // JSON nulls are gaps in the series (e.g. a benchmark that did not
        // exist yet) — never coerce them through Number(), since Number(null)
        // is 0 and would draw a fake flat zero line.
        const raw = row[column];
        if (raw === null || raw === undefined || raw === "") return null;
        const value = Number(raw);
        return Number.isFinite(value) ? value : null;
      }),
    })),
  }, true);
}

function resizeInteractiveCharts() {
  interactiveCharts.forEach((entry) => entry.chart.resize());
}

// Re-render with fresh theme colors (called by theme.js after palette changes).
function rethemeInteractiveCharts() {
  interactiveCharts.forEach((entry, elementId) => {
    renderInteractiveChart(elementId, entry.rows, entry.columns, entry.options);
  });
}
window.rethemeInteractiveCharts = rethemeInteractiveCharts;

async function loadBenchmarks(event) {
  if (event) event.preventDefault();
  const button = document.getElementById("benchmarkButton");
  const status = document.getElementById("benchmarkStatus");
  const keys = [...document.querySelectorAll('input[name="benchKey"]:checked')].map((input) => input.value);
  if (!keys.length) {
    toast("Select at least one benchmark");
    return;
  }
  button.disabled = true;
  status.textContent = "Comparing";
  startTaskProgress("taskProgress", "Comparing against benchmarks...");
  try {
    const refresh = document.getElementById("benchmarkRefresh").value === "true";
    const result = await fetchJson(`/api/benchmarks?keys=${keys.join(",")}&refresh=${refresh}`);
    const body = document.getElementById("benchmarkBody");
    body.innerHTML = "";
    (result.summary || []).forEach((row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${row.benchmark || row.key}</td>
        <td>${formatByType(row.observations, "integer")}</td>
        <td>${formatPct(row.strategy_cagr)}</td>
        <td>${formatPct(row.benchmark_cagr)}</td>
        <td>${formatNumber(row.benchmark_sharpe)}</td>
        <td>${formatPct(row.benchmark_max_drawdown)}</td>
        <td>${formatNumber(row.correlation)}</td>
        <td>${formatNumber(row.beta)}</td>
        <td>${formatPct(row.alpha_annualized)}</td>
        <td>${formatNumber(row.information_ratio)}</td>
        <td>${formatNumber(row.up_capture)}</td>
        <td>${formatNumber(row.down_capture)}</td>
      `;
      body.appendChild(tr);
    });
    const curves = result.curves || [];
    const columns = curves.length
      ? Object.keys(curves[0]).filter((key) => key !== "date")
      : [];
    renderInteractiveChart("benchmarkChart", curves, columns, {
      yFormatter: (value) => `$${formatNumber(value, 2)}`,
      emptyText: "Run a benchmark comparison to load curves",
    });
    status.textContent = `${(result.summary || []).length} benchmarks`;
    if ((result.unknown_keys || []).length) {
      toast(`Unknown benchmark keys ignored: ${result.unknown_keys.join(", ")}`);
    }
    finishTaskProgress("taskProgress", "Benchmark comparison complete");
  } catch (error) {
    status.textContent = "Failed";
    finishTaskProgress("taskProgress", "Benchmark comparison failed", true);
    toast(`Benchmark comparison failed: ${error.message}`);
  } finally {
    button.disabled = false;
  }
}

async function runWalkforward(event) {
  if (event) event.preventDefault();
  const button = document.getElementById("walkforwardButton");
  const status = document.getElementById("walkforwardStatus");
  button.disabled = true;
  status.textContent = "Running";
  startTaskProgress("taskProgress", "Running walk-forward folds...");
  try {
    const maxFolds = Number(document.getElementById("wfMaxFolds").value || 0);
    const result = await fetchJson("/api/walkforward", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        train_days: Number(document.getElementById("wfTrainDays").value || 756),
        test_days: Number(document.getElementById("wfTestDays").value || 63),
        step_days: Number(document.getElementById("wfStepDays").value || 63),
        max_folds: maxFolds > 0 ? maxFolds : null,
        start_date: document.getElementById("wfStartDate").value || null,
        selection_metric: document.getElementById("wfMetric").value || "sharpe",
        cost_model: document.getElementById("wfCostModel").value || "flat",
      }),
    });
    const grid = document.getElementById("walkforwardGrid");
    grid.innerHTML = "";
    const metrics = result.oos_metrics || {};
    const tiles = [
      ["OOS Sharpe", metrics.sharpe, "number"],
      ["OOS CAGR", metrics.cagr, "pct"],
      ["OOS Max Drawdown", metrics.max_drawdown, "pct"],
      ["Avg In-Sample Train Sharpe", result.in_sample_average_sharpe, "number"],
    ];
    tiles.forEach(([label, value, type]) => {
      const tile = document.createElement("article");
      tile.className = "metric";
      tile.innerHTML = `
        <div class="metric-label">${label}</div>
        <div class="metric-value">${formatByType(value, type)}</div>
      `;
      grid.appendChild(tile);
    });
    const meta = document.getElementById("walkforwardMeta");
    if (meta && metrics.sharpe !== null && metrics.sharpe !== undefined && result.in_sample_average_sharpe) {
      const decay = 1 - Number(metrics.sharpe) / Number(result.in_sample_average_sharpe);
      meta.textContent = Number.isFinite(decay)
        ? `in-sample to out-of-sample Sharpe decay ${formatPct(decay, 0)}`
        : "";
    }
    const body = document.getElementById("walkforwardBody");
    body.innerHTML = "";
    (result.folds || []).forEach((row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${row.fold}</td>
        <td>${row.train_start} to ${row.train_end}</td>
        <td>${row.test_start} to ${row.test_end}</td>
        <td>${row.lookback_days}</td>
        <td>${row.top_n}</td>
        <td>${formatNumber(row.train_metric)}</td>
        <td>${formatNumber(row.oos_sharpe)}</td>
        <td>${formatPct(row.oos_cagr)}</td>
        <td>${formatPct(row.oos_max_drawdown)}</td>
      `;
      body.appendChild(tr);
    });
    renderInteractiveChart("walkforwardChart", result.oos_curve || [], ["equity"], {
      yFormatter: (value) => formatCompactMoney(value) || formatMoney(value),
      emptyText: "Run walk-forward to load the out-of-sample curve",
    });
    status.textContent = `${(result.folds || []).length} folds`;
    finishTaskProgress("taskProgress", "Walk-forward complete");
    toast("Walk-forward complete");
  } catch (error) {
    status.textContent = "Failed";
    finishTaskProgress("taskProgress", "Walk-forward failed", true);
    toast(`Walk-forward failed: ${error.message}`);
  } finally {
    button.disabled = false;
  }
}

document.getElementById("refreshButton").addEventListener("click", () => {
  loadDashboard().then(() => toast("Dashboard refreshed")).catch((error) => toast(error.message));
});
document.getElementById("backtestForm").addEventListener("submit", rerun);
document.getElementById("benchmarkForm").addEventListener("submit", loadBenchmarks);
document.getElementById("walkforwardForm").addEventListener("submit", runWalkforward);
document.getElementById("dataForm").addEventListener("submit", downloadRealData);
document.getElementById("portfolioForm").addEventListener("submit", buildPortfolio);
document.getElementById("downloadBuilderSummaryCsv").addEventListener("click", downloadBuilderSummaryCsv);
document.getElementById("downloadBuilderWeightsCsv").addEventListener("click", downloadBuilderWeightsCsv);
document.getElementById("addUniverseButton").addEventListener("click", addUniverseSelection);
document.getElementById("refreshUniverseButton").addEventListener("click", () => {
  loadUniverse(true).then(() => toast("Universe refreshed")).catch((error) => toast(error.message));
});
document.getElementById("universeMode").addEventListener("change", syncUniverseMode);
document.getElementById("dataSource").addEventListener("change", syncDataSourceStart);
["dataStart", "dataEnd", "dataTickers"].forEach((id) => {
  document.getElementById(id).addEventListener("change", syncSignalWindowFromDownloadInputs);
});
document.getElementById("builderDataSource").addEventListener("change", syncBuilderDataSourceStart);
document.getElementById("useAllHistory").addEventListener("change", syncLookbackMode);
document.getElementById("refreshHistory").addEventListener("change", syncBuilderHistoryControls);
["tradeSymbolFilter", "tradeStartFilter", "tradeEndFilter", "tradePnlFilter", "tradeLimitFilter"].forEach((id) => {
  document.getElementById(id).addEventListener("input", () => {
    loadTradesFromFilters().catch((error) => toast(error.message));
  });
  document.getElementById(id).addEventListener("change", () => {
    loadTradesFromFilters().catch((error) => toast(error.message));
  });
});
document.getElementById("clearTradeFilters").addEventListener("click", () => {
  document.getElementById("tradeSymbolFilter").value = "";
  document.getElementById("tradeStartFilter").value = "";
  document.getElementById("tradeEndFilter").value = "";
  document.getElementById("tradePnlFilter").value = "all";
  document.getElementById("tradeLimitFilter").value = "1000";
  loadTradesFromFilters().then(() => syncTradeDateDefaults(state.tradeSummary)).catch((error) => toast(error.message));
});
document.getElementById("downloadTradesCsv").addEventListener("click", downloadTradesCsv);
document.querySelectorAll("[data-tab]").forEach((button) => {
  button.addEventListener("click", () => activateTab(button.dataset.tab || "overview"));
});
document.querySelectorAll("[data-goto-tab]").forEach((button) => {
  button.addEventListener("click", () => activateTab(button.dataset.gotoTab || "overview"));
});
document.querySelectorAll("[data-subtab]").forEach((button) => {
  button.addEventListener("click", () => {
    const tab = button.closest("[data-tab-panel]")?.dataset.tabPanel;
    if (tab) activateSubpanel(tab, button.dataset.subtab);
  });
});

const PORTFOLIO_PRESETS = {
  conservative: {
    maxWeight: 0.05,
    kellyFraction: 0.25,
    meanVarianceRiskAversion: 12,
    blackLittermanRiskAversion: 12,
    cvarAlpha: 0.95,
  },
  balanced: {
    maxWeight: 0.12,
    kellyFraction: 0.5,
    meanVarianceRiskAversion: 8,
    blackLittermanRiskAversion: 8,
    cvarAlpha: 0.95,
  },
  aggressive: {
    maxWeight: 0.2,
    kellyFraction: 1.0,
    meanVarianceRiskAversion: 4,
    blackLittermanRiskAversion: 4,
    cvarAlpha: 0.975,
  },
};

document.querySelectorAll("[data-preset]").forEach((button) => {
  button.addEventListener("click", () => {
    const preset = PORTFOLIO_PRESETS[button.dataset.preset];
    if (!preset) return;
    Object.entries(preset).forEach(([id, value]) => setNumberInput(id, value));
    document.querySelectorAll("[data-preset]").forEach((other) => {
      other.classList.toggle("active", other === button);
    });
    toast(`Applied ${button.dataset.preset} preset`);
  });
});
document.querySelectorAll(".curve-toolbar [data-range]").forEach((button) => {
  button.addEventListener("click", () => {
    state.curves.range = button.dataset.range || "full";
    state.curves.hoverIndex = null;
    renderCurves();
  });
});
["equityChart", "drawdownChart"].forEach((id) => {
  const canvas = document.getElementById(id);
  canvas.addEventListener("pointermove", handleCurvePointerMove);
  canvas.addEventListener("pointerleave", handleCurvePointerLeave);
});
window.addEventListener("resize", () => {
  renderCurves();
  resizeInteractiveCharts();
});

loadDashboard()
  .then(() => loadUniverse(false))
  .then(() => {
    syncUniverseMode();
    syncBuilderHistoryControls();
    document.getElementById("builderStatus").textContent = "Ready";
  })
  .catch((error) => toast(error.message));

// ===================== RESEARCH FINDINGS: ERA STUDY =====================
function eraSurvivalCell(milestone) {
  if (!milestone) return '<span class="gain">never</span>';
  return `<span class="loss">${milestone.date} (${milestone.months} mo)</span>`;
}

function renderEraStudy(study) {
  if (!study) return;
  const eras = (study.eras || []).filter((era) => !era.empty);
  const meta = document.getElementById("eraStudyMeta");
  if (meta) {
    const windowText = study.data_window ? `${study.data_window.start} → ${study.data_window.end}` : "";
    meta.textContent = `Generated ${study.generated_at || "-"} | ${windowText} | initial stake $${formatNumber(study.initial_capital || 0, 0)} per era | strategy defaults: ${study.strategy?.lookback_days}D lookback, top ${study.strategy?.top_n}`;
  }

  const costBody = document.getElementById("eraCostBody");
  if (costBody) {
    costBody.innerHTML = "";
    eras.forEach((era) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${era.name}</td>
        <td>${era.start} → ${era.end}</td>
        <td>${formatNumber(era.fees_bps, 1)}</td>
        <td>${formatNumber(era.slippage_bps, 1)}</td>
        <td><strong>${formatNumber(era.cost_bps_per_side, 1)} bps</strong></td>
        <td>≈ ${formatNumber(era.cost_bps_per_side * 2, 0)} bps</td>
        <td class="subtle">${era.key === "1900-01-01" ? "Pre-May Day fixed rates" : era.name}</td>
      `;
      costBody.appendChild(tr);
    });
  }

  const body = document.getElementById("eraStudyBody");
  if (body) {
    body.innerHTML = "";
    eras.forEach((era) => {
      const netClass = era.net_total_return > 0 ? "gain" : "loss";
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${era.name}</td>
        <td>${era.start} → ${era.end}</td>
        <td>${formatNumber(era.cost_bps_per_side, 1)} bps</td>
        <td class="gain">${formatPct(era.gross_total_return)}</td>
        <td class="${netClass}">${era.net_total_return <= -0.9999 ? "wipeout" : formatPct(era.net_total_return)}</td>
        <td class="${netClass}">${era.net_cagr == null ? "—" : formatPct(era.net_cagr)}</td>
        <td>${era.net_sharpe == null ? "—" : formatNumber(era.net_sharpe)}</td>
        <td class="loss">${formatPct(era.net_max_drawdown)}</td>
        <td>${eraSurvivalCell(era.halved)}</td>
        <td>${eraSurvivalCell(era.ruined)}</td>
        <td><strong>${era.verdict}</strong></td>
      `;
      body.appendChild(tr);
    });
  }

  const conclusion = document.getElementById("eraStudyConclusion");
  if (conclusion && study.conclusion) {
    const c = study.conclusion;
    const wipeouts = eras.filter((era) => era.ruined).length;
    const survivors = eras.filter((era) => era.net_total_return > 0);
    const fastest = eras.filter((era) => era.ruined).sort((a, b) => a.ruined.months - b.ruined.months)[0];
    const grossNote = c.gross_edge_all_eras
      ? "The raw overnight edge — before any costs — was positive in every single era tested. The signal itself was never the problem."
      : "The gross edge was not positive in every era, so the signal itself was uneven across history.";
    const survivalNote = c.first_profitable_era
      ? `The edge first survives its costs in the <strong>${c.first_profitable_era}</strong> era (from ${c.first_profitable_start}). ${survivors.map((s) => `${s.name}: ${formatPct(s.net_cagr)} CAGR, Sharpe ${formatNumber(s.net_sharpe)}`).join("; ")}.`
      : "The edge never survives its costs in any tested era.";
    const wipeoutNote = fastest
      ? ` In the earliest eras the stake dies fast: at 90 bps per side, $10,000 was halved in under 2 months and 90% gone in about half a year (${fastest.name}: ruined ${fastest.ruined.date}, ${fastest.ruined.months} months).`
      : "";
    conclusion.innerHTML = `
      <p><strong>What the study shows.</strong> ${grossNote} Costs decide everything.</p>
      <p><strong>Era by era.</strong> ${wipeouts} of ${eras.length} eras end in effective ruin (90%+ loss).${wipeoutNote}
      Through the 1997–2001 and decimalization eras the bleed slows — 20 then 10 bps per side still grinds the stake down, just over years instead of months.</p>
      <p><strong>Where it starts working.</strong> ${survivalNote}</p>
      <p><strong>The lesson.</strong> This strategy is not a 1960s strategy, a 1980s strategy, or a 1990s strategy — it is a product of modern
      market structure. Its entire existence depends on sub-penny spreads and near-zero commissions, and its capacity is bounded by the same
      overnight liquidity that makes those costs possible. Backtested at any earlier era's prices, the same signals would not have made a
      fortune slowly; they would have lost one quickly.</p>
      <p class="subtle">This is a research finding about cost structure, not investment advice. Era rates are approximations — override them in config/settings.yml and rerun to test sensitivity.</p>
    `;
  }

  const status = document.getElementById("eraStudyStatus");
  if (status) status.textContent = `${eras.length} eras tested`;
  state.eraStudyLoaded = true;
  renderEraStudyChart(eras);
}

function renderEraStudyChart(eras) {
  const el = document.getElementById("eraStudyChart");
  if (!el || typeof echarts === "undefined") return;
  let entry = interactiveCharts.get("eraStudyChart");
  if (!entry) {
    entry = { chart: echarts.init(el, null, { renderer: "canvas" }), rows: [], columns: [], options: {} };
    interactiveCharts.set("eraStudyChart", entry);
  }
  const colors = chartThemeColors();
  const labels = eras.map((era) => era.name);
  const netValues = eras.map((era) => (era.net_cagr == null ? -100 : era.net_cagr * 100));
  const grossValues = eras.map((era) => (era.gross_cagr == null ? null : era.gross_cagr * 100));
  entry.chart.setOption({
    backgroundColor: "transparent",
    animationDuration: 400,
    grid: { left: 64, right: 24, top: 44, bottom: 90 },
    legend: {
      top: 4,
      icon: "roundRect",
      itemWidth: 14,
      itemHeight: 4,
      textStyle: { color: colors.muted, fontSize: 12 },
    },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      backgroundColor: "rgba(10, 14, 26, 0.92)",
      borderColor: colors.border,
      textStyle: { color: "#e9eef8", fontSize: 12 },
      valueFormatter: (value) => (value === null || value === undefined ? "—" : `${formatNumber(value, 1)}%`),
    },
    xAxis: {
      type: "category",
      data: labels,
      axisLabel: { color: colors.muted, fontSize: 11, interval: 0, rotate: 24 },
      axisLine: { lineStyle: { color: colors.border } },
      axisTick: { show: false },
    },
    yAxis: {
      type: "value",
      axisLabel: { color: colors.muted, fontSize: 11, formatter: (value) => `${value}%` },
      splitLine: { lineStyle: { color: colors.border } },
    },
    series: [
      {
        name: "Gross CAGR (before costs)",
        type: "bar",
        data: grossValues,
        itemStyle: { color: "rgba(167, 139, 250, 0.55)", borderRadius: [4, 4, 0, 0] },
      },
      {
        name: "Net CAGR (after era costs)",
        type: "bar",
        data: netValues.map((value) => ({
          value,
          itemStyle: { color: value >= 0 ? "#34d399" : "#fb7185", borderRadius: [4, 4, 0, 0] },
        })),
      },
    ],
  }, true);
}

async function loadEraStudy() {
  const status = document.getElementById("eraStudyStatus");
  const result = await fetchJson("/api/era-study");
  if (result.status !== "ok") {
    if (status) status.textContent = "Not run yet";
    return;
  }
  renderEraStudy(result.study);
}

async function runEraStudy() {
  const button = document.getElementById("eraStudyButton");
  const status = document.getElementById("eraStudyStatus");
  button.disabled = true;
  if (status) status.textContent = "Running";
  startTaskProgress("taskProgress", "Running era study (full backtest, ~1 min)...");
  try {
    const result = await fetchJson("/api/era-study/run", { method: "POST" });
    renderEraStudy(result.study);
    finishTaskProgress("taskProgress", "Era study complete");
    toast("Era study complete");
  } catch (error) {
    if (status) status.textContent = "Failed";
    finishTaskProgress("taskProgress", "Era study failed", true);
    toast(`Era study failed: ${error.message}`);
  } finally {
    button.disabled = false;
  }
}

document.getElementById("eraStudyButton")?.addEventListener("click", runEraStudy);

// ===================== SIGNAL -> OPTIMIZER BRIDGE =====================
function optimizeCurrentCandidates() {
  const holdings = state.overview?.latest_holdings || [];
  const symbols = [...new Set(holdings.map((row) => row.symbol).filter(Boolean))];
  if (!symbols.length) {
    toast("No current candidates — run the signal backtest first");
    return;
  }
  document.getElementById("universeMode").value = "selected";
  document.getElementById("returnModel").value = "overnight";
  document.getElementById("portfolioTickers").value = symbols.join(", ");
  activateTab("portfolio");
  toast(`Loaded ${symbols.length} signal candidates into the builder — optimizing`);
  document.getElementById("portfolioForm").requestSubmit();
}

document.getElementById("optimizeCandidatesButton")?.addEventListener("click", optimizeCurrentCandidates);
