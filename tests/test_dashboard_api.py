import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from nightfall_alpha.config import (
    BacktestSettings,
    PortfolioSettings,
    ProjectSettings,
    Settings,
    StrategySettings,
    UniverseSettings,
)
from nightfall_alpha.data.pipeline import run_research_pipeline
from nightfall_alpha.dashboard.app import (
    PortfolioBuilderRequest,
    _effective_portfolio_lookback,
    _missing_symbols_from_prices,
    _should_refresh_portfolio_history,
)


class DashboardPipelineTests(unittest.TestCase):
    def test_portfolio_builder_lookback_is_separate_from_refresh_window(self) -> None:
        cached_request = PortfolioBuilderRequest(
            symbols="AAPL,MSFT",
            data_source="yahoo",
            refresh_history=False,
            lookback_days=60,
        )
        refresh_request = PortfolioBuilderRequest(
            symbols="AAPL,MSFT",
            data_source="yahoo",
            refresh_history=True,
            lookback_days=60,
        )
        max_history_request = PortfolioBuilderRequest(
            symbols="AAPL,MSFT",
            data_source="yahoo_max",
            refresh_history=False,
            lookback_days=60,
        )
        full_history_request = PortfolioBuilderRequest(
            symbols="AAPL,MSFT",
            data_source="yahoo_max",
            refresh_history=True,
            lookback_days=None,
        )

        self.assertEqual(_effective_portfolio_lookback(cached_request), 60)
        self.assertEqual(_effective_portfolio_lookback(refresh_request), 60)
        self.assertEqual(_effective_portfolio_lookback(max_history_request), 60)
        self.assertIsNone(_effective_portfolio_lookback(full_history_request))

    def test_portfolio_builder_data_source_does_not_force_refresh(self) -> None:
        cached_long_history_request = PortfolioBuilderRequest(
            symbols="AAPL,MSFT",
            data_source="yahoo_max",
            refresh_history=False,
            lookback_days=None,
        )
        stooq_cached_request = PortfolioBuilderRequest(
            symbols="AAPL,MSFT",
            data_source="stooq",
            refresh_history=False,
            lookback_days=None,
        )
        explicit_refresh_request = PortfolioBuilderRequest(
            symbols="AAPL,MSFT",
            data_source="yahoo_max",
            refresh_history=True,
            lookback_days=None,
        )

        self.assertFalse(_should_refresh_portfolio_history(cached_long_history_request))
        self.assertFalse(_should_refresh_portfolio_history(stooq_cached_request))
        self.assertTrue(_should_refresh_portfolio_history(explicit_refresh_request))

    def test_portfolio_builder_missing_symbols_use_loaded_cache(self) -> None:
        prices = pd.DataFrame({"symbol": ["AAPL", "MSFT", "AAPL"]})

        missing = _missing_symbols_from_prices(prices, ("AAPL", "MSFT", "NVDA"))

        self.assertEqual(missing, ["NVDA"])

    def test_signal_backtest_overrides_update_strategy_context(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            universe_path = root / "universe.csv"
            universe_path.write_text(
                "symbol,name,sector\nAAA,AAA Corp,Technology\nBBB,BBB Corp,Financials\nCCC,CCC Corp,Healthcare\n",
                encoding="utf-8",
            )
            settings = Settings(
                project=ProjectSettings(data_dir=root),
                universe=UniverseSettings(sample_file=universe_path, live_file=root / "missing.csv"),
                backtest=BacktestSettings(initial_capital=100_000.0, fees_bps=0.5, slippage_bps=1.0),
                strategy=StrategySettings(lookback_days=20, min_history=10, top_n=3, max_weight=0.2, min_signal=-10.0),
                portfolio=PortfolioSettings(),
            )

            result = run_research_pipeline(
                settings,
                force_sample_prices=True,
                symbols_limit=3,
                start="2024-01-01",
                end="2024-06-30",
                strategy_overrides={
                    "lookback_days": 8,
                    "min_history": 4,
                    "top_n": 2,
                    "max_weight": 0.4,
                    "min_signal": -10.0,
                },
                price_start="2024-03-01",
                price_end="2024-05-31",
                initial_capital=250_000.0,
                fees_bps=2.0,
                slippage_bps=3.0,
            )

            self.assertEqual(result["strategy"]["top_n"], 2)
            self.assertEqual(result["metrics"]["initial_capital"], 250_000.0)
            self.assertEqual(result["metrics"]["backtest"]["initial_capital"], 250_000.0)
            self.assertEqual(result["metrics"]["backtest"]["fees_bps"], 2.0)
            self.assertEqual(result["metrics"]["backtest"]["slippage_bps"], 3.0)
            if not result["backtest"].daily.empty:
                self.assertAlmostEqual(float(result["backtest"].daily.iloc[0]["starting_equity"]), 250_000.0)
            self.assertGreaterEqual(result["data_window"]["start"], "2024-03-01")
            self.assertLessEqual(result["data_window"]["end"], "2024-05-31")

            signals = result["signals"]
            max_per_day = int(signals.groupby("signal_date").size().max()) if not signals.empty else 0
            self.assertLessEqual(max_per_day, 2)


if __name__ == "__main__":
    unittest.main()
