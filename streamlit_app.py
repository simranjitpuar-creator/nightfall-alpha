from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st


ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nightfall_alpha.backtest.metrics import compute_drawdown
from nightfall_alpha.config import Settings, load_settings
from nightfall_alpha.dashboard.app import (
    _filter_trades_frame,
    _load_payload,
    _missing_symbols_from_prices,
    _trade_summary,
)
from nightfall_alpha.data.pipeline import (
    artifact_paths,
    download_real_market_data,
    ensure_price_history_for_symbols,
    load_or_create_prices,
    run_research_pipeline,
)
from nightfall_alpha.data.schema import normalize_symbol
from nightfall_alpha.data.universe_metadata import load_universe_metadata
from nightfall_alpha.portfolio.builder import PortfolioBuildSpec, build_custom_portfolio, parse_symbols
from nightfall_alpha.portfolio.optimizers import OptimizerSuiteSettings


st.set_page_config(
    page_title="NightFall Alpha",
    layout="wide",
    initial_sidebar_state="expanded",
)


METRIC_SPECS = [
    ("Initial Equity", "initial_capital", "money"),
    ("Ending Equity", "final_equity", "money"),
    ("Total Return", "total_return", "pct_signed"),
    ("CAGR", "cagr", "pct_signed"),
    ("Annual Vol", "annualized_volatility", "pct"),
    ("Sharpe", "sharpe", "number"),
    ("Sortino", "sortino", "number"),
    ("Calmar", "calmar", "number"),
    ("1Y Roll Sharpe", "rolling_sharpe_1y", "number"),
    ("3Y Roll Sharpe", "rolling_sharpe_3y", "number"),
    ("5Y Roll Sharpe", "rolling_sharpe_5y", "number"),
    ("1Y Roll Sortino", "rolling_sortino_1y", "number"),
    ("3Y Roll Sortino", "rolling_sortino_3y", "number"),
    ("5Y Roll Sortino", "rolling_sortino_5y", "number"),
    ("1Y Roll Calmar", "rolling_calmar_1y", "number"),
    ("3Y Roll Calmar", "rolling_calmar_3y", "number"),
    ("5Y Roll Calmar", "rolling_calmar_5y", "number"),
    ("Max DD", "max_drawdown", "pct_signed"),
    ("Win Rate", "win_rate", "pct"),
    ("Profit Factor", "profit_factor", "number"),
    ("VaR 95", "var_95", "pct_signed"),
    ("CVaR 95", "cvar_95", "pct_signed"),
    ("Cost Drag", "total_cost_return", "pct"),
    ("Avg Exposure", "exposure", "pct"),
    ("Avg Turnover", "average_round_trip_turnover", "pct"),
]

PORTFOLIO_COLUMNS = [
    "portfolio",
    "start_date",
    "end_date",
    "elapsed_years",
    "observations",
    "initial_capital",
    "final_equity",
    "total_return",
    "cagr",
    "annualized_return",
    "annualized_volatility",
    "sharpe",
    "sortino",
    "calmar",
    "rolling_sharpe_1y",
    "rolling_sharpe_3y",
    "rolling_sharpe_5y",
    "rolling_sortino_1y",
    "rolling_sortino_3y",
    "rolling_sortino_5y",
    "rolling_calmar_1y",
    "rolling_calmar_3y",
    "rolling_calmar_5y",
    "max_drawdown",
    "var_95",
    "cvar_95",
    "win_rate",
    "profit_factor",
    "total_cost_return",
    "weight_sum",
    "cash_weight",
    "max_weight_limit",
    "max_weight",
    "rebalance_count",
    "average_turnover",
    "positions",
    "optimizer_parameters",
]


def inject_css() -> None:
    st.markdown(
        """
        <style>
        :root {
          --nf-bg: #070b16;
          --nf-bg-2: #0b1120;
          --nf-panel: rgba(255, 255, 255, 0.045);
          --nf-panel-2: rgba(255, 255, 255, 0.07);
          --nf-border: rgba(255, 255, 255, 0.10);
          --nf-line: rgba(255, 255, 255, 0.08);
          --nf-text: #e9eef8;
          --nf-strong: #ffffff;
          --nf-muted: #8a94ac;
          --nf-accent: #6366f1;
          --nf-accent-2: #22d3ee;
          --nf-gain: #34d399;
          --nf-loss: #fb7185;
        }
        .stApp {
          background:
            radial-gradient(1100px 700px at 100% -10%, rgba(99, 102, 241, 0.16), transparent 60%),
            radial-gradient(900px 600px at -5% 110%, rgba(34, 211, 238, 0.10), transparent 55%),
            var(--nf-bg);
          color: var(--nf-text);
        }
        [data-testid="stSidebar"] {
          background: linear-gradient(160deg, rgba(255,255,255,.055), rgba(255,255,255,.015));
          border-right: 1px solid var(--nf-border);
        }
        [data-testid="stSidebar"] * { color: var(--nf-text); }
        [data-testid="stSidebar"] [role="radiogroup"] label {
          border: 1px solid transparent;
          border-radius: 12px;
          padding: 8px 10px;
          margin: 3px 0;
        }
        [data-testid="stSidebar"] [role="radiogroup"] label:hover {
          background: rgba(255,255,255,.045);
          border-color: rgba(99,102,241,.25);
        }
        h1, h2, h3, h4 { color: var(--nf-strong); letter-spacing: 0; }
        .block-container { padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1760px; }
        .nf-brand {
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 8px 4px 18px;
          margin-bottom: 8px;
          border-bottom: 1px solid var(--nf-line);
        }
        .nf-mark {
          width: 42px;
          height: 42px;
          display: grid;
          place-items: center;
          border-radius: 12px;
          background: linear-gradient(150deg, rgba(99,102,241,.22), rgba(34,211,238,.18));
          border: 1px solid var(--nf-border);
          color: var(--nf-accent-2);
          font-weight: 900;
        }
        .nf-brand-name { font-size: 16px; font-weight: 800; color: var(--nf-strong); }
        .nf-brand-tag { font-size: 11px; color: var(--nf-muted); font-weight: 600; }
        .nf-panel {
          padding: 18px 20px;
          border: 1px solid var(--nf-border);
          border-radius: 16px;
          background: linear-gradient(160deg, rgba(255,255,255,.055), rgba(255,255,255,.015));
          box-shadow: 0 18px 40px -24px rgba(0,0,0,.8);
          margin-bottom: 18px;
        }
        .nf-heading {
          display: flex;
          align-items: flex-end;
          justify-content: space-between;
          gap: 14px;
          margin-bottom: 14px;
        }
        .nf-subtle {
          color: var(--nf-muted);
          font-size: 12px;
          font-weight: 600;
        }
        .nf-metric-grid {
          display: grid;
          grid-template-columns: repeat(6, minmax(140px, 1fr));
          gap: 14px;
          margin: 12px 0 18px;
        }
        .nf-card {
          position: relative;
          min-height: 88px;
          padding: 15px 16px;
          border-radius: 10px;
          background: linear-gradient(160deg, rgba(255,255,255,.055), rgba(255,255,255,.015));
          border: 1px solid var(--nf-border);
          overflow: hidden;
        }
        .nf-card:before {
          content: "";
          position: absolute;
          inset: 0 0 auto 0;
          height: 2px;
          background: linear-gradient(90deg, var(--nf-accent), var(--nf-accent-2));
          opacity: .7;
        }
        .nf-label {
          color: var(--nf-muted);
          font-size: 11.5px;
          font-weight: 700;
          text-transform: uppercase;
        }
        .nf-value {
          margin-top: 10px;
          font-family: "JetBrains Mono", ui-monospace, monospace;
          font-size: 22px;
          font-weight: 800;
          color: var(--nf-strong);
        }
        .nf-gain { color: var(--nf-gain); }
        .nf-loss { color: var(--nf-loss); }
        .stButton > button, .stDownloadButton > button {
          min-height: 40px;
          border-radius: 12px;
          border: 1px solid rgba(255,255,255,.12);
          background: linear-gradient(120deg, var(--nf-accent), color-mix(in srgb, var(--nf-accent) 55%, var(--nf-accent-2)));
          color: #fff;
          font-weight: 800;
          box-shadow: 0 10px 24px -12px rgba(99,102,241,.9);
        }
        .stButton > button[kind="secondary"], .stDownloadButton > button[kind="secondary"] {
          background: rgba(255,255,255,.045);
          color: var(--nf-text);
          box-shadow: none;
        }
        div[data-baseweb="input"] > div,
        div[data-baseweb="select"] > div,
        textarea {
          background: rgba(255,255,255,.045) !important;
          border-color: rgba(255,255,255,.12) !important;
          border-radius: 8px !important;
        }
        .stDataFrame {
          border: 1px solid var(--nf-border);
          border-radius: 12px;
          overflow: hidden;
        }
        .nf-help {
          color: var(--nf-muted);
          font-size: 12.5px;
          line-height: 1.55;
        }
        @media (max-width: 1180px) {
          .nf-metric-grid { grid-template-columns: repeat(3, minmax(132px, 1fr)); }
        }
        @media (max-width: 760px) {
          .nf-metric-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def settings() -> Settings:
    return load_settings(ROOT / "config" / "settings.yml")


def money(value: Any, digits: int = 0) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    return f"${number:,.{digits}f}"


def number(value: Any, digits: int = 2) -> str:
    try:
        number_value = float(value)
    except (TypeError, ValueError):
        return "-"
    return f"{number_value:,.{digits}f}"


def pct(value: Any, digits: int = 2) -> str:
    try:
        number_value = float(value)
    except (TypeError, ValueError):
        return "-"
    return f"{number_value * 100:.{digits}f}%"


def metric_value(value: Any, value_type: str) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "-"
    if value_type == "text":
        return str(value)
    if value_type == "money":
        return money(value, 0)
    if value_type in {"pct", "pct_signed"}:
        return pct(value)
    if value_type == "integer":
        return number(value, 0)
    return number(value)


def tone_class(value: Any, value_type: str) -> str:
    if "signed" not in value_type:
        return ""
    try:
        number_value = float(value)
    except (TypeError, ValueError):
        return ""
    if number_value > 0:
        return " nf-gain"
    if number_value < 0:
        return " nf-loss"
    return ""


def metric_grid(source: dict[str, Any], specs: list[tuple[str, str, str]] = METRIC_SPECS) -> None:
    cards = []
    for label, key, value_type in specs:
        value = source.get(key)
        cards.append(
            f"""
            <div class="nf-card">
              <div class="nf-label">{label}</div>
              <div class="nf-value{tone_class(value, value_type)}">{metric_value(value, value_type)}</div>
            </div>
            """
        )
    st.markdown(f'<div class="nf-metric-grid">{"".join(cards)}</div>', unsafe_allow_html=True)


def page_heading(title: str, subtitle: str | None = None) -> None:
    st.markdown(
        f"""
        <div class="nf-heading">
          <div>
            <h1 style="margin-bottom: 2px;">{title}</h1>
            <div class="nf-subtle">{subtitle or ""}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def to_csv(frame: pd.DataFrame) -> bytes:
    return frame.where(pd.notna(frame), "").to_csv(index=False).encode("utf-8")


def display_frame(frame: pd.DataFrame, *, height: int = 420, columns: list[str] | None = None) -> None:
    if frame.empty:
        st.info("No rows available yet.")
        return
    show = frame.copy()
    if columns:
        show = show[[column for column in columns if column in show.columns]]
    st.dataframe(show, use_container_width=True, height=height)


def current_payload(cfg: Settings) -> dict[str, Any]:
    return _load_payload(cfg)


def project_path(path: Path) -> str:
    resolved_root = ROOT.resolve()
    resolved_path = Path(path).resolve()
    try:
        return resolved_path.relative_to(resolved_root).as_posix()
    except ValueError:
        return Path(path).as_posix()


def plot_curves(equity: pd.DataFrame) -> None:
    if equity.empty:
        st.info("Run a signal backtest to generate curves.")
        return
    curve = equity.copy()
    curve["date"] = pd.to_datetime(curve["date"], errors="coerce")
    curve = curve.dropna(subset=["date"]).sort_values("date")
    if "drawdown" not in curve:
        curve["drawdown"] = compute_drawdown(pd.to_numeric(curve["equity"], errors="coerce"))

    equity_fig = go.Figure()
    equity_fig.add_trace(
        go.Scatter(
            x=curve["date"],
            y=curve["equity"],
            mode="lines",
            name="Equity",
            line={"color": "#22d3ee", "width": 2.4},
            fill="tozeroy",
            fillcolor="rgba(34, 211, 238, 0.10)",
        )
    )
    equity_fig.update_layout(
        title="Signal Strategy Equity Curve",
        xaxis_title="Exit Date",
        yaxis_title="Portfolio Equity",
        hovermode="x unified",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(255,255,255,0.02)",
        font={"color": "#e9eef8"},
        margin={"l": 50, "r": 24, "t": 55, "b": 45},
    )
    equity_fig.update_yaxes(tickprefix="$", gridcolor="rgba(255,255,255,0.08)")
    equity_fig.update_xaxes(gridcolor="rgba(255,255,255,0.08)")

    drawdown_fig = go.Figure()
    drawdown_fig.add_trace(
        go.Scatter(
            x=curve["date"],
            y=curve["drawdown"],
            mode="lines",
            name="Drawdown",
            line={"color": "#fb7185", "width": 2.2},
            fill="tozeroy",
            fillcolor="rgba(251, 113, 133, 0.18)",
        )
    )
    drawdown_fig.update_layout(
        title="Signal Strategy Drawdown Curve",
        xaxis_title="Exit Date",
        yaxis_title="Drawdown",
        hovermode="x unified",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(255,255,255,0.02)",
        font={"color": "#e9eef8"},
        margin={"l": 50, "r": 24, "t": 55, "b": 45},
    )
    drawdown_fig.update_yaxes(tickformat=".1%", gridcolor="rgba(255,255,255,0.08)")
    drawdown_fig.update_xaxes(gridcolor="rgba(255,255,255,0.08)")

    left, right = st.columns([1.35, 1.0])
    left.plotly_chart(equity_fig, use_container_width=True)
    right.plotly_chart(drawdown_fig, use_container_width=True)


def market_data_page(cfg: Settings) -> None:
    page_heading("Market Data", "Refresh Yahoo or Stooq daily OHLCV data, then optionally rerun the signal backtest.")
    with st.form("market_data_form"):
        col1, col2, col3, col4 = st.columns(4)
        source_label = col1.selectbox(
            "Source",
            ["Yahoo Finance", "Yahoo Max History", "Stooq Long History"],
            help="Selects the provider used to refresh the local daily OHLCV cache. Longer history can change signals, optimizer inputs, covariance, VaR, CVaR, and drawdowns.",
        )
        tickers = col2.text_input(
            "Tickers",
            "",
            help="Optional comma-separated tickers. Leave blank to use the S&P 500 universe file.",
        )
        start = col3.date_input(
            "Start",
            value=pd.Timestamp("2018-01-01").date(),
            help="First date requested from the provider. Actual coverage may begin later if the symbol has shorter history.",
        )
        end_enabled = col4.checkbox("Set end date", value=False)
        end_value = col4.date_input("End", value=pd.Timestamp.today().date(), disabled=not end_enabled)
        limit = col1.number_input(
            "Limit",
            min_value=1,
            max_value=505,
            value=50,
            help="Maximum number of S&P 500 symbols to download when Tickers is blank. Ignored for a typed ticker list.",
        )
        run_after = col2.checkbox(
            "Run backtest",
            value=True,
            help="When enabled, the refreshed price window is passed into the signal engine so metrics, curves, candidates, and blotter update together.",
        )

        with st.expander("Signal settings used if Run backtest is enabled", expanded=False):
            s1, s2, s3, s4 = st.columns(4)
            initial_capital = s1.number_input("Initial Equity", min_value=1.0, value=1_000_000.0, step=10_000.0)
            fees_bps = s2.number_input("Fees Bps", min_value=0.0, value=0.5, step=0.1)
            slippage_bps = s3.number_input("Slippage Bps", min_value=0.0, value=1.0, step=0.1)
            lookback = s4.number_input("Signal Lookback", min_value=2, value=63, step=1)
            s5, s6, s7, s8 = st.columns(4)
            min_history = s5.number_input("Min History", min_value=1, value=40, step=1)
            top_n = s6.number_input("Top N", min_value=1, max_value=505, value=25, step=1)
            max_weight = s7.number_input("Max Weight", min_value=0.01, max_value=1.0, value=0.07, step=0.01)
            min_signal = s8.number_input("Min Signal", value=0.0, step=0.1)

        submitted = st.form_submit_button("Download Real Data")

    if not submitted:
        return

    source = {"Yahoo Finance": "yahoo", "Yahoo Max History": "yahoo_max", "Stooq Long History": "stooq"}[source_label]
    progress = st.progress(0, text="Preparing market data request...")
    try:
        symbols = list(parse_symbols(tickers)) if tickers.strip() else None
        progress.progress(20, text="Downloading market data...")
        result = download_real_market_data(
            cfg,
            symbols=symbols,
            start=str(start),
            end=str(end_value) if end_enabled else None,
            symbols_limit=None if symbols else int(limit),
            refresh_universe=symbols is None,
            merge_existing=True,
            source=source,
        )
        progress.progress(70, text="Merging and validating price cache...")
        if run_after:
            progress.progress(82, text="Running signal backtest...")
            run_research_pipeline(
                cfg,
                strategy_overrides={
                    "lookback_days": int(lookback),
                    "min_history": int(min_history),
                    "top_n": int(top_n),
                    "max_weight": float(max_weight),
                    "min_signal": float(min_signal),
                },
                initial_capital=float(initial_capital),
                fees_bps=float(fees_bps),
                slippage_bps=float(slippage_bps),
                price_start=str(start),
                price_end=str(end_value) if end_enabled else None,
                price_symbols=result.returned_symbols,
            )
        progress.progress(100, text="Market data updated.")
        missing = f" Missing: {len(result.missing_symbols)}." if result.missing_symbols else ""
        st.success(f"Updated {len(result.returned_symbols)} symbols and {len(result.prices):,} cache rows.{missing}")
    except Exception as exc:
        progress.empty()
        st.error(f"Market data refresh failed: {exc}")


def signal_page(cfg: Settings) -> None:
    payload = current_payload(cfg)
    data_window = payload.get("data_window") or {}
    strategy = payload.get("strategy") or {}
    backtest = payload.get("backtest") or {}
    subtitle = "No current book"
    if payload.get("latest_signal_date"):
        subtitle = f"Current book date {payload['latest_signal_date']} | {strategy.get('lookback_days', 63)}D signal lookback"
    page_heading("Signal Backtest", subtitle)

    with st.form("signal_backtest_form"):
        c1, c2, c3, c4 = st.columns(4)
        initial_capital = c1.number_input(
            "Initial Equity",
            min_value=1.0,
            value=float(backtest.get("initial_capital") or 1_000_000.0),
            step=10_000.0,
            help="Starting dollar value. It scales the equity curve and PnL, but not percentage returns or weights.",
        )
        fees_bps = c2.number_input(
            "Fees Bps",
            min_value=0.0,
            value=float(backtest.get("fees_bps") or 0.5),
            step=0.1,
            help="Explicit trading fee assumption in basis points per side. Higher values reduce net returns and trade PnL.",
        )
        slippage_bps = c3.number_input(
            "Slippage Bps",
            min_value=0.0,
            value=float(backtest.get("slippage_bps") or 1.0),
            step=0.1,
            help="Execution slippage in basis points per side. Used with fees in the round-trip cost model.",
        )
        lookback = c4.number_input(
            "Signal Lookback",
            min_value=2,
            value=int(strategy.get("lookback_days") or 63),
            step=1,
            help="Recent trading-day window used to calculate each stock's rolling overnight score.",
        )
        c5, c6, c7, c8 = st.columns(4)
        min_history = c5.number_input("Min History", min_value=1, value=int(strategy.get("min_history") or 40), step=1)
        top_n = c6.number_input("Top N", min_value=1, max_value=505, value=int(strategy.get("top_n") or 25), step=1)
        max_weight = c7.number_input(
            "Max Weight",
            min_value=0.01,
            max_value=1.0,
            value=float(strategy.get("max_weight") or 0.07),
            step=0.01,
        )
        min_signal = c8.number_input("Min Signal", value=float(strategy.get("min_signal") or 0.0), step=0.1)
        c9, c10, c11 = st.columns([1, 1, 2])
        price_start = c9.text_input("Price Start", value=str(data_window.get("requested_start") or ""))
        price_end = c10.text_input("Price End", value=str(data_window.get("requested_end") or ""))
        price_tickers = c11.text_input("Price Tickers", value="")
        submitted = st.form_submit_button("Run Signal Backtest")

    if submitted:
        progress = st.progress(0, text="Loading selected price window...")
        try:
            progress.progress(35, text="Generating overnight signals...")
            result = run_research_pipeline(
                cfg,
                strategy_overrides={
                    "lookback_days": int(lookback),
                    "min_history": int(min_history),
                    "top_n": int(top_n),
                    "max_weight": float(max_weight),
                    "min_signal": float(min_signal),
                },
                initial_capital=float(initial_capital),
                fees_bps=float(fees_bps),
                slippage_bps=float(slippage_bps),
                price_start=price_start.strip() or None,
                price_end=price_end.strip() or None,
                price_symbols=list(parse_symbols(price_tickers)) if price_tickers.strip() else None,
            )
            progress.progress(100, text="Backtest complete.")
            st.success(f"Backtest complete with {len(result['backtest'].trades):,} trade rows.")
            payload = current_payload(cfg)
        except Exception as exc:
            progress.empty()
            st.error(f"Signal backtest failed: {exc}")

    st.markdown('<div class="nf-panel">', unsafe_allow_html=True)
    st.markdown("### Signal Strategy Backtest Metrics")
    metric_grid(payload.get("metrics") or {})
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="nf-panel">', unsafe_allow_html=True)
    plot_curves(payload.get("equity", pd.DataFrame()))
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="nf-panel">', unsafe_allow_html=True)
    holdings = payload.get("latest_holdings", pd.DataFrame())
    st.markdown("### Current Overnight Candidates")
    display_frame(
        holdings,
        height=430,
        columns=[
            "signal_date",
            "exit_date",
            "signal_rank",
            "symbol",
            "name",
            "sector",
            "sector_code",
            "market_cap",
            "weight",
            "overnight_sharpe",
            "overnight_mean",
            "overnight_volatility",
            "lookback_win_rate",
            "next_overnight_return",
        ],
    )
    st.markdown("</div>", unsafe_allow_html=True)


def universe_options(cfg: Settings) -> tuple[pd.DataFrame, dict[str, str]]:
    universe = load_universe_metadata(cfg, refresh_market_caps=False)
    labels: dict[str, str] = {}
    for _, row in universe.iterrows():
        symbol = str(row.get("symbol", ""))
        sector = str(row.get("sector_code") or "OTHER")
        name = str(row.get("name") or symbol)
        cap = row.get("market_cap")
        cap_text = ""
        if pd.notna(cap):
            cap_number = float(cap)
            if cap_number >= 1_000_000_000_000:
                cap_text = f" | ${cap_number / 1_000_000_000_000:.1f}T"
            elif cap_number >= 1_000_000_000:
                cap_text = f" | ${cap_number / 1_000_000_000:.1f}B"
            elif cap_number >= 1_000_000:
                cap_text = f" | ${cap_number / 1_000_000:.0f}M"
        cached = " | cached" if bool(row.get("in_price_cache")) else ""
        labels[f"{sector} | {symbol} | {name}{cap_text}{cached}"] = symbol
    return universe, labels


def portfolio_page(cfg: Settings) -> None:
    page_heading("Portfolio Research", "Build every optimizer at once from selected stocks or the entire local universe.")
    try:
        universe, label_to_symbol = universe_options(cfg)
    except Exception:
        universe, label_to_symbol = pd.DataFrame(), {}

    with st.form("portfolio_form"):
        c1, c2, c3, c4 = st.columns(4)
        universe_mode = c1.selectbox(
            "Universe Mode",
            ["Selected Stocks", "Entire Local Universe"],
            help="Selected Stocks uses typed and selected names. Entire Local Universe uses every symbol currently in the local price cache.",
        )
        data_source = c2.selectbox(
            "Missing Data",
            ["Yahoo Finance", "Yahoo Max History", "Stooq Long History"],
            index=1,
            help="Provider used when selected symbols are missing or Refresh History is enabled.",
        )
        return_model = c3.selectbox(
            "Return Model",
            ["Overnight", "Close to Close"],
            help="Overnight uses close-to-next-open returns. Close to Close uses ordinary daily close-to-close returns.",
        )
        rebalance = c4.selectbox("Rebalance", ["Static Weights", "Monthly", "Quarterly", "Annually"])
        tickers = st.text_area(
            "Tickers",
            value="AAPL, MSFT, NVDA, AMZN, JPM, XOM, PG, UNH",
            height=72,
            disabled=universe_mode == "Entire Local Universe",
            help="Comma-separated selected-stock universe for optimizer runs.",
        )
        selected_labels = st.multiselect(
            "Universe Selector",
            options=list(label_to_symbol),
            disabled=universe_mode == "Entire Local Universe",
            help="Optional picker organized by sector code and sorted by market cap when available.",
        )
        c5, c6, c7, c8 = st.columns(4)
        initial_capital = c5.number_input("Initial Equity", min_value=1.0, value=1_000_000.0, step=10_000.0)
        fees_bps = c6.number_input("Fees Bps", min_value=0.0, value=0.0, step=0.1)
        slippage_bps = c7.number_input("Slippage Bps", min_value=0.0, value=0.0, step=0.1)
        default_max_weight = c8.number_input("Default Max Weight", min_value=0.01, max_value=1.0, value=0.15, step=0.01)
        c9, c10, c11, c12 = st.columns(4)
        use_all_history = c9.checkbox("Use All History", value=False)
        lookback = c10.number_input("Lookback", min_value=20, value=756, step=21, disabled=use_all_history)
        data_since = c11.text_input("Data Since", value="2010-01-01")
        auto_fill = c12.checkbox("Auto-fill Missing", value=True)
        refresh_history = st.checkbox("Refresh History", value=False)

        with st.expander("Optimizer parameters", expanded=True):
            p1, p2, p3, p4 = st.columns(4)
            kelly_fraction = p1.number_input("Kelly Fraction", min_value=0.0, max_value=1.0, value=0.5, step=0.05)
            kelly_cap = p2.number_input("Kelly Max Weight", min_value=0.0, max_value=1.0, value=0.0, step=0.01)
            mean_risk = p3.number_input("Mean Variance Risk Aversion", min_value=0.01, value=8.0, step=0.5)
            mean_cap = p4.number_input("Mean Variance Max Weight", min_value=0.0, max_value=1.0, value=0.0, step=0.01)
            p5, p6, p7, p8 = st.columns(4)
            minvar_cap = p5.number_input("Minimum Variance Max Weight", min_value=0.0, max_value=1.0, value=0.0, step=0.01)
            invvol_cap = p6.number_input("Inverse Volatility Max Weight", min_value=0.0, max_value=1.0, value=0.0, step=0.01)
            cvar_alpha = p7.number_input("CVaR Alpha", min_value=0.51, max_value=0.999, value=0.95, step=0.01)
            cvar_cap = p8.number_input("CVaR Max Weight", min_value=0.0, max_value=1.0, value=0.0, step=0.01)
            p9, p10, p11, p12 = st.columns(4)
            bl_tau = p9.number_input("Black-Litterman Tau", min_value=0.001, value=0.05, step=0.01)
            bl_prior_risk = p10.number_input("BL Prior Risk Aversion", min_value=0.01, value=2.5, step=0.25)
            bl_risk = p11.number_input("BL Optimizer Risk Aversion", min_value=0.01, value=8.0, step=0.5)
            bl_cap = p12.number_input("Black-Litterman Max Weight", min_value=0.0, max_value=1.0, value=0.0, step=0.01)

        submitted = st.form_submit_button("Build Portfolio")

    if submitted:
        source = {"Yahoo Finance": "yahoo", "Yahoo Max History": "yahoo_max", "Stooq Long History": "stooq"}[data_source]
        return_model_key = "close_to_close" if return_model == "Close to Close" else "overnight"
        rebalance_key = {"Static Weights": "none", "Monthly": "monthly", "Quarterly": "quarterly", "Annually": "annually"}[rebalance]
        progress = st.progress(0, text="Loading price cache...")
        try:
            prices = load_or_create_prices(cfg)
            progress.progress(20, text="Resolving portfolio universe...")
            if universe_mode == "Entire Local Universe":
                symbols = tuple(sorted(prices["symbol"].dropna().astype(str).map(normalize_symbol).unique()))
            else:
                picked = [label_to_symbol[label] for label in selected_labels]
                symbols = tuple(dict.fromkeys([*parse_symbols(tickers), *picked]))

            missing = _missing_symbols_from_prices(prices, symbols)
            downloaded: list[str] = []
            if symbols and (refresh_history or (auto_fill and missing)):
                progress.progress(38, text="Fetching missing or refreshed history...")
                prices, missing, downloaded = ensure_price_history_for_symbols(
                    cfg,
                    symbols,
                    start=data_since,
                    source=source,
                    refresh_existing=refresh_history,
                )

            def cap_value(value: float) -> float | None:
                return None if float(value) <= 0 else float(value)

            progress.progress(62, text="Running optimizer suite...")
            result = build_custom_portfolio(
                prices,
                PortfolioBuildSpec(
                    symbols=symbols,
                    method="best",
                    return_model=return_model_key,
                    rebalance_frequency=rebalance_key,
                    max_weight=float(default_max_weight),
                    optimizer_settings=OptimizerSuiteSettings(
                        default_max_weight=float(default_max_weight),
                        kelly_fraction=float(kelly_fraction),
                        kelly_max_weight=cap_value(kelly_cap),
                        mean_variance_risk_aversion=float(mean_risk),
                        mean_variance_max_weight=cap_value(mean_cap),
                        minimum_variance_max_weight=cap_value(minvar_cap),
                        inverse_volatility_max_weight=cap_value(invvol_cap),
                        cvar_alpha=float(cvar_alpha),
                        cvar_max_weight=cap_value(cvar_cap),
                        black_litterman_tau=float(bl_tau),
                        black_litterman_prior_risk_aversion=float(bl_prior_risk),
                        black_litterman_risk_aversion=float(bl_risk),
                        black_litterman_max_weight=cap_value(bl_cap),
                    ),
                    risk_free_rate=cfg.portfolio.risk_free_rate,
                    initial_capital=float(initial_capital),
                    fees_bps=float(fees_bps),
                    slippage_bps=float(slippage_bps),
                    lookback_days=None if use_all_history else int(lookback),
                    allow_symbol_filtering=universe_mode == "Entire Local Universe",
                ),
            )
            result["initial_capital"] = float(initial_capital)
            result["fees_bps"] = float(fees_bps)
            result["slippage_bps"] = float(slippage_bps)
            result["missing_symbols"] = missing
            result["downloaded_symbols"] = downloaded
            st.session_state["builder"] = result
            progress.progress(100, text="Portfolio built.")
            st.success(f"Built all optimizers. Best Sharpe: {result['selected_portfolio']}")
        except Exception as exc:
            progress.empty()
            st.error(f"Portfolio builder failed: {exc}")

    result = st.session_state.get("builder")
    if result:
        summary = result["summary"].copy()
        weights = result["weights"].copy()
        st.markdown('<div class="nf-panel">', unsafe_allow_html=True)
        st.markdown(
            f"### Current Builder Optimizer Suite\n"
            f"<div class='nf-subtle'>{result.get('return_model')} | {result.get('rebalance_frequency')} | "
            f"{len(result.get('symbols', [])):,} symbols | {result.get('start_date')} to {result.get('end_date')}</div>",
            unsafe_allow_html=True,
        )
        display_frame(summary, height=360, columns=PORTFOLIO_COLUMNS)
        st.download_button(
            "Download Portfolio Metrics CSV",
            data=to_csv(summary),
            file_name="nightfall_alpha_portfolio_metrics.csv",
            mime="text/csv",
        )
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="nf-panel">', unsafe_allow_html=True)
        st.markdown("### Optimizer Weights")
        for portfolio in summary["portfolio"].dropna().astype(str).tolist():
            group = weights[weights["portfolio"] == portfolio].copy()
            if group.empty:
                continue
            if "rebalance_date" in group and group["rebalance_date"].notna().any():
                latest = group["rebalance_date"].dropna().astype(str).max()
                group = group[group["rebalance_date"].astype(str) == latest]
                label = f"{portfolio} | latest rebalance {latest} | {len(group)} positions"
            else:
                label = f"{portfolio} | {len(group)} positions"
            with st.expander(label, expanded=portfolio == result.get("selected_portfolio")):
                display_frame(group.sort_values("weight", ascending=False), height=260)
        st.download_button(
            "Download Portfolio Executions CSV",
            data=to_csv(weights),
            file_name="nightfall_alpha_portfolio_executions.csv",
            mime="text/csv",
        )
        st.markdown("</div>", unsafe_allow_html=True)

    payload = current_payload(cfg)
    saved_summary = payload.get("portfolio_summary", pd.DataFrame())
    if not saved_summary.empty:
        st.markdown('<div class="nf-panel">', unsafe_allow_html=True)
        st.markdown("### Saved Signal Universe Suite")
        display_frame(saved_summary, height=300, columns=PORTFOLIO_COLUMNS)
        st.markdown("</div>", unsafe_allow_html=True)


def trade_page(cfg: Settings) -> None:
    payload = current_payload(cfg)
    trades = payload.get("trades", pd.DataFrame()).copy()
    page_heading("Trade Blotter", "Linked to the latest saved Signal Backtest executions.")
    if trades.empty:
        st.info("No signal trade rows are available yet.")
        return

    default_start, default_end = None, None
    for column in ("exit_date", "signal_date"):
        if column in trades:
            dates = pd.to_datetime(trades[column], errors="coerce").dropna()
            if not dates.empty:
                default_start = dates.min().date()
                default_end = dates.max().date()
                break

    c1, c2, c3, c4, c5 = st.columns([1.4, 1, 1, 1, 1])
    symbol = c1.text_input("Symbol", "", help="Filters rows by ticker text.")
    start = c2.date_input("From", value=default_start) if default_start else None
    end = c3.date_input("To", value=default_end) if default_end else None
    pnl_filter = c4.selectbox("PnL", ["All", "Wins", "Losses"])
    limit = c5.selectbox("Rows", [100, 500, 1000, 5000, 10000], index=2)

    filtered = _filter_trades_frame(
        trades,
        start=str(start) if start else None,
        end=str(end) if end else None,
        symbol=symbol or None,
        pnl=pnl_filter.lower(),
    )
    shown = filtered.tail(int(limit))
    summary = _trade_summary(trades, filtered, shown)
    trade_specs = [
        ("Source Trades", "source_total_trades", "integer"),
        ("Filtered Trades", "filtered_trades", "integer"),
        ("Loaded Rows", "returned_trades", "integer"),
        ("Symbols", "filtered_symbols", "integer"),
        ("Source Start", "source_start_date", "text"),
        ("Source End", "source_end_date", "text"),
        ("Latest Exit", "latest_exit_date", "text"),
        ("Latest Book Trades", "latest_trade_count", "integer"),
        ("Win Rate", "win_rate", "pct"),
        ("Total Net PnL", "total_net_pnl", "money"),
        ("Avg Trade PnL", "average_trade_pnl", "money"),
        ("Best Trade", "best_trade_pnl", "money"),
        ("Worst Trade", "worst_trade_pnl", "money"),
        ("Total Costs", "total_cost", "money"),
        ("Avg Weight", "average_weight", "pct"),
    ]
    st.markdown('<div class="nf-panel">', unsafe_allow_html=True)
    metric_grid(summary, trade_specs)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="nf-panel">', unsafe_allow_html=True)
    st.markdown(
        f"### Signal Backtest Executions\n<div class='nf-subtle'>{len(shown):,} shown | {len(filtered):,} filtered | "
        f"{len(trades):,} source rows</div>",
        unsafe_allow_html=True,
    )
    display_frame(shown, height=520)
    st.download_button(
        "Download Filtered Trade Blotter CSV",
        data=to_csv(filtered),
        file_name="nightfall_alpha_trade_blotter.csv",
        mime="text/csv",
    )
    st.markdown("</div>", unsafe_allow_html=True)


def framework_page() -> None:
    page_heading("Framework", "Methodology, assumptions, parameters, outputs, and limitations.")
    st.markdown(
        """
        <div class="nf-panel">
        <h3>Market Data</h3>
        <p class="nf-help">
        NightFall Alpha stores normalized daily OHLCV bars in <code>data/processed/prices.csv</code>.
        The Streamlit deployment does not include your local cache, so refreshes happen inside the app runtime.
        Yahoo Finance is the default source, Yahoo Max requests the longest available Yahoo history, and Stooq
        can provide longer free daily history when automated access is accepted by the provider. The S&P 500
        universe comes from the committed universe CSV or a refreshed Wikipedia-derived S&P table when available.
        </p>
        </div>

        <div class="nf-panel">
        <h3>Signal Backtest</h3>
        <p class="nf-help">
        The strategy calculates close-to-next-open overnight returns, ranks symbols by rolling overnight
        behavior, buys the selected book near the close, and exits near the next open. Signal Lookback controls
        the rolling estimation window, Min History removes thin symbols, Top N controls breadth, Max Weight
        caps concentration, and Min Signal filters weak scores. The equity curve compounds net returns after
        fees and slippage. Drawdown measures the fall from prior equity peaks.
        </p>
        </div>

        <div class="nf-panel">
        <h3>Portfolio Research</h3>
        <p class="nf-help">
        The builder runs every optimizer from the same return matrix and settings. Kelly targets growth,
        Mean Variance balances return against variance using a risk-aversion coefficient, Minimum Variance
        minimizes volatility, Inverse Volatility favors lower-volatility assets, CVaR Aware focuses on tail
        losses, and Black-Litterman uses a simplified covariance-implied prior before mean-variance allocation.
        Static portfolios optimize once; monthly, quarterly, and annual modes re-optimize through time.
        </p>
        </div>

        <div class="nf-panel">
        <h3>Trade Blotter And Costs</h3>
        <p class="nf-help">
        The trade blotter is generated by the Signal Backtest, not the Portfolio Builder. Notional equals
        starting equity times target weight. Gross PnL equals notional times realized overnight return.
        Signal costs are modeled as a round trip: <code>2 * gross exposure * (fees bps + slippage bps) / 10000</code>.
        Portfolio Research costs are based on allocation and rebalance turnover.
        </p>
        </div>

        <div class="nf-panel">
        <h3>Limitations</h3>
        <p class="nf-help">
        Results can suffer from survivorship bias, free-provider data gaps, opening auction fill assumptions,
        simplified transaction costs, optimizer instability, overfitting, and regime change. This is a research
        dashboard, not a live trading system. Live or paper trading still needs broker risk controls, order
        staging, reconciliation, kill switches, audit logs, and compliance review.
        </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def settings_page() -> None:
    page_heading("Settings", "Streamlit uses the NightFall Alpha visual theme and a fixed deployment palette.")
    paths = artifact_paths(settings())
    st.markdown('<div class="nf-panel">', unsafe_allow_html=True)
    st.write("Local runtime paths are intentionally not displayed in the deployed app or README.")
    st.write("Generated data, reports, logs, and virtual environments are ignored by Git.")
    st.write("Current artifact folders are created by the running environment when needed.")
    st.code(
        "\n".join(
            [
                f"prices: {project_path(paths.prices_path)}",
                f"reports: {project_path(paths.daily_path.parent)}",
                "streamlit entrypoint: streamlit_app.py",
            ]
        )
    )
    st.markdown("</div>", unsafe_allow_html=True)


def sidebar_nav() -> str:
    st.sidebar.markdown(
        """
        <div class="nf-brand">
          <div class="nf-mark">NF</div>
          <div>
            <div class="nf-brand-name">NightFall Alpha</div>
            <div class="nf-brand-tag">Overnight Alpha Desk</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    return st.sidebar.radio(
        "Dashboard sections",
        ["Market Data", "Signal Backtest", "Portfolio Research", "Trade Blotter", "Framework", "Settings"],
        index=1,
        label_visibility="collapsed",
    )


def main() -> None:
    inject_css()
    cfg = settings()
    selected = sidebar_nav()
    try:
        if selected == "Market Data":
            market_data_page(cfg)
        elif selected == "Signal Backtest":
            signal_page(cfg)
        elif selected == "Portfolio Research":
            portfolio_page(cfg)
        elif selected == "Trade Blotter":
            trade_page(cfg)
        elif selected == "Framework":
            framework_page()
        else:
            settings_page()
    except Exception as exc:
        st.error(f"NightFall Alpha could not load this page: {exc}")


if __name__ == "__main__":
    main()
