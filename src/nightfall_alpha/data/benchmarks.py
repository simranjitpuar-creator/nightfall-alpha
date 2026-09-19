"""Benchmark downloads and relative-performance analytics.

Benchmarks are fetched with yfinance and cached as parquet under
data/cache/benchmarks/. The UST10Y entry converts the ^TNX constant-maturity
yield index into an approximate 10-year Treasury total-return series using
a fixed modified duration; treat it as a rough comparison, not an investable
index.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

BENCHMARKS: dict[str, dict[str, str]] = {
    "SP500": {"ticker": "^GSPC", "name": "S&P 500", "kind": "price"},
    "SP100": {"ticker": "^OEX", "name": "S&P 100", "kind": "price"},
    "NASDAQ": {"ticker": "^IXIC", "name": "Nasdaq Composite", "kind": "price"},
    "MSCI_WORLD": {
        "ticker": "URTH",
        "name": "MSCI World (URTH ETF proxy, from 2012)",
        "kind": "price",
    },
    "UST10Y": {
        "ticker": "^TNX",
        "name": "US 10Y Treasury (approx. total return from ^TNX)",
        "kind": "yield",
    },
}

UST10Y_DURATION = 8.0  # approximate modified duration for a 10y note


@dataclass(frozen=True)
class BenchmarkSeries:
    key: str
    name: str
    returns: pd.Series  # daily simple returns indexed by date


def _cache_dir(data_dir: Path) -> Path:
    path = Path(data_dir) / "cache" / "benchmarks"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _cache_path(data_dir: Path, key: str) -> Path:
    return _cache_dir(data_dir) / f"{key}.parquet"


def _download_close(ticker: str, start: str = "1900-01-01") -> pd.Series:
    import yfinance as yf

    frame = yf.download(ticker, start=start, auto_adjust=True, progress=False)
    if frame.empty:
        raise ValueError(f"No data returned for benchmark ticker {ticker}")
    close = frame["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    close.index = pd.to_datetime(close.index).normalize()
    close = close.dropna()
    return close.astype(float)


def _yield_to_total_return(close: pd.Series) -> pd.Series:
    """Approximate 10y Treasury daily total return from the ^TNX yield index."""
    y = close / 1000.0  # ^TNX is quoted as yield * 10, e.g. 45.0 = 4.50%
    y = y.where(y > 0).ffill()
    carry = y.shift(1) / 365.25
    price_move = -UST10Y_DURATION * y.diff()
    return (carry + price_move).dropna()


def load_benchmark(
    key: str,
    data_dir: Path,
    *,
    refresh: bool = False,
    start: str = "1900-01-01",
) -> BenchmarkSeries:
    if key not in BENCHMARKS:
        raise ValueError(f"Unknown benchmark '{key}'. Choices: {', '.join(BENCHMARKS)}")
    spec = BENCHMARKS[key]
    cache_path = _cache_path(data_dir, key)

    close: pd.Series | None = None
    if cache_path.exists() and not refresh:
        cached = pd.read_parquet(cache_path)
        close = pd.Series(cached["close"].to_numpy(dtype=float), index=pd.to_datetime(cached["date"]))

    if close is None:
        close = _download_close(spec["ticker"], start=start)
        if cache_path.exists():  # incremental refresh: append only new dates
            cached = pd.read_parquet(cache_path)
            old = pd.Series(cached["close"].to_numpy(dtype=float), index=pd.to_datetime(cached["date"]))
            close = pd.concat([old, close[close.index > old.index.max()]]) if len(old) else close
            close = close[~close.index.duplicated(keep="last")].sort_index()
        pd.DataFrame({"date": close.index, "close": close.to_numpy()}).to_parquet(cache_path, index=False)

    if spec["kind"] == "yield":
        returns = _yield_to_total_return(close)
    else:
        returns = close.pct_change().dropna()
    returns = returns.replace([np.inf, -np.inf], np.nan).dropna()
    return BenchmarkSeries(key=key, name=spec["name"], returns=returns)


def available_cached_benchmarks(data_dir: Path) -> list[str]:
    cache = _cache_dir(data_dir)
    return sorted(path.stem for path in cache.glob("*.parquet") if path.stem in BENCHMARKS)


def relative_metrics(
    strategy_returns: pd.Series,
    benchmark_returns: pd.Series,
    *,
    periods_per_year: int = 252,
    risk_free_rate: float = 0.0,
) -> dict[str, float | None]:
    """Align strategy and benchmark daily returns and compute comparison stats."""
    strategy = strategy_returns.dropna()
    strategy = strategy[~strategy.index.duplicated(keep="last")]
    benchmark = benchmark_returns.dropna()
    benchmark = benchmark[~benchmark.index.duplicated(keep="last")]
    joined = pd.concat([strategy, benchmark], axis=1, keys=["strategy", "benchmark"]).dropna()
    if len(joined) < 20:
        return {}

    s = joined["strategy"]
    b = joined["benchmark"]

    n = len(joined)
    strat_total = float((1.0 + s).prod() - 1.0)
    bench_total = float((1.0 + b).prod() - 1.0)
    years = n / float(periods_per_year)
    strat_cagr = (1.0 + strat_total) ** (1.0 / years) - 1.0 if years > 0 and strat_total > -1 else None
    bench_cagr = (1.0 + bench_total) ** (1.0 / years) - 1.0 if years > 0 and bench_total > -1 else None

    bench_vol = float(b.std(ddof=0) * math.sqrt(periods_per_year))
    bench_sharpe = (float(b.mean() * periods_per_year) - risk_free_rate) / bench_vol if bench_vol > 0 else None
    bench_equity = (1.0 + b).cumprod()
    bench_max_dd = float((bench_equity / bench_equity.cummax() - 1.0).min())

    covariance = float(np.cov(s, b, ddof=0)[0, 1])
    bench_var = float(b.var(ddof=0))
    beta = covariance / bench_var if bench_var > 0 else None
    correlation = float(s.corr(b))

    diff = s - b
    tracking_error = float(diff.std(ddof=0) * math.sqrt(periods_per_year))
    alpha = float(s.mean() * periods_per_year) - (beta or 0.0) * float(b.mean() * periods_per_year)
    information_ratio = float(diff.mean() * periods_per_year) / tracking_error if tracking_error > 0 else None

    up = joined[b > 0]
    down = joined[b < 0]
    up_capture = float(up["strategy"].mean() / up["benchmark"].mean()) if len(up) and up["benchmark"].mean() != 0 else None
    down_capture = (
        float(down["strategy"].mean() / down["benchmark"].mean()) if len(down) and down["benchmark"].mean() != 0 else None
    )

    return {
        "observations": n,
        "strategy_total_return": strat_total,
        "benchmark_total_return": bench_total,
        "strategy_cagr": strat_cagr,
        "benchmark_cagr": bench_cagr,
        "benchmark_volatility": bench_vol,
        "benchmark_sharpe": bench_sharpe,
        "benchmark_max_drawdown": bench_max_dd,
        "correlation": correlation,
        "beta": beta,
        "alpha_annualized": alpha,
        "tracking_error": tracking_error,
        "information_ratio": information_ratio,
        "up_capture": up_capture,
        "down_capture": down_capture,
    }


def benchmark_comparison(
    strategy_returns: pd.Series,
    data_dir: Path,
    keys: list[str],
    *,
    refresh: bool = False,
    risk_free_rate: float = 0.0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compare a strategy return series against several benchmarks.

    Returns (summary_table, aligned_curves) where aligned_curves has one
    cumulative-growth column per key plus 'strategy', indexed by date.
    """
    rows: list[dict[str, object]] = []
    curves: dict[str, pd.Series] = {}
    strategy = strategy_returns.dropna().sort_index()
    strategy = strategy[~strategy.index.duplicated(keep="last")]
    if strategy.empty:
        return pd.DataFrame(rows), pd.DataFrame()

    # Curves are clipped to the strategy's live window and rebased to exactly
    # 1.0 at each series' first in-window date. Benchmarks with longer history
    # (e.g. the S&P 500 back to 1928) no longer stretch the chart's x-axis, and
    # dates without data stay NaN so the chart renders gaps, not zeros.
    window_start, window_end = strategy.index.min(), strategy.index.max()

    strategy_curve = (1.0 + strategy).cumprod()
    curves["strategy"] = strategy_curve / strategy_curve.iloc[0]

    for key in keys:
        try:
            series = load_benchmark(key, data_dir, refresh=refresh)
        except Exception:
            continue
        metrics = relative_metrics(strategy, series.returns, risk_free_rate=risk_free_rate)
        if not metrics:
            continue
        rows.append({"key": key, "benchmark": series.name, **metrics})
        benchmark_returns = series.returns[~series.returns.index.duplicated(keep="last")].sort_index()
        benchmark_curve = (1.0 + benchmark_returns).cumprod()
        benchmark_curve = benchmark_curve[
            (benchmark_curve.index >= window_start) & (benchmark_curve.index <= window_end)
        ]
        if benchmark_curve.empty:
            continue
        curves[key] = benchmark_curve / benchmark_curve.iloc[0]

    aligned = pd.DataFrame(curves).dropna(how="all")
    return pd.DataFrame(rows), aligned
