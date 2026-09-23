from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from nightfall_alpha.data.synthetic import SyntheticMarketConfig, generate_synthetic_ohlcv
from nightfall_alpha.research.signal_portfolio import (
    OPTIMIZER_METHODS,
    SignalPortfolioConfig,
    run_signal_portfolio_backtest,
)


def _prices(symbols: int = 30, start: str = "2023-01-01", end: str = "2024-06-30", seed: int = 11) -> pd.DataFrame:
    return generate_synthetic_ohlcv(
        [f"TST{i:02d}" for i in range(symbols)],
        SyntheticMarketConfig(start=start, end=end, seed=seed),
    )


class SignalPortfolioEngineTests(unittest.TestCase):
    def test_all_methods_run_and_produce_consistent_shapes(self) -> None:
        prices = _prices()
        for method in OPTIMIZER_METHODS:
            with self.subTest(method=method):
                result = run_signal_portfolio_backtest(
                    prices, SignalPortfolioConfig(method=method, top_n=10, max_weight=0.07)
                )
                daily = result["daily"]
                self.assertGreater(len(daily), 50)
                self.assertTrue({"signal_date", "exit_date", "net_return", "ending_equity"} <= set(daily.columns))
                # Equity compounds with net returns.
                np.testing.assert_allclose(
                    daily["ending_equity"].to_numpy(),
                    daily["starting_equity"].to_numpy() * (1.0 + daily["net_return"].to_numpy()),
                    rtol=1e-9,
                )
                # Net = gross + cash - cost.
                np.testing.assert_allclose(
                    daily["net_return"].to_numpy(),
                    daily["gross_return"].to_numpy()
                    + daily["cash_weight"].to_numpy() * 0.0
                    - daily["cost_return"].to_numpy(),
                    rtol=1e-9,
                )
                self.assertEqual(len(result["current_book"]), 10)
                self.assertIn("sharpe", result["metrics"])

    def test_weights_respect_cap_and_book_size(self) -> None:
        prices = _prices()
        result = run_signal_portfolio_backtest(
            prices, SignalPortfolioConfig(method="mean_variance", top_n=12, max_weight=0.09)
        )
        book = result["current_book"]
        self.assertLessEqual(len(book), 12)
        self.assertLessEqual(float(book["optimizer_weight"].max()), 0.09 + 1e-9)
        self.assertLessEqual(float(book["optimizer_weight"].sum()), 1.0 + 1e-9)

    def test_first_night_bills_full_allocation(self) -> None:
        prices = _prices()
        result = run_signal_portfolio_backtest(
            prices, SignalPortfolioConfig(method="equal_weight", top_n=10, max_weight=0.07, fees_bps=10.0, slippage_bps=0.0)
        )
        first = result["daily"].iloc[0]
        # Day one turnover equals the full invested weight...
        self.assertAlmostEqual(float(first["turnover"]), float(first["weight_sum"]), places=9)
        # ...and cost is turnover times the uniform fee rate.
        self.assertAlmostEqual(float(first["cost_return"]), float(first["turnover"]) * 10.0 / 10_000.0, places=9)

    def test_zero_costs_means_zero_cost_return(self) -> None:
        prices = _prices()
        result = run_signal_portfolio_backtest(
            prices, SignalPortfolioConfig(method="score_weighted", top_n=10, max_weight=0.07, fees_bps=0.0, slippage_bps=0.0)
        )
        self.assertAlmostEqual(float(result["daily"]["cost_return"].abs().sum()), 0.0, places=12)

    def test_methods_differentiate_when_cap_has_headroom(self) -> None:
        prices = _prices()
        configs = {
            method: SignalPortfolioConfig(method=method, top_n=25, max_weight=0.07)
            for method in ("equal_weight", "minimum_variance", "kelly")
        }
        equities = {
            method: run_signal_portfolio_backtest(prices, cfg)["metrics"]["final_equity"]
            for method, cfg in configs.items()
        }
        values = list(equities.values())
        self.assertGreater(max(values) - min(values), 1.0)

    def test_invalid_method_rejected(self) -> None:
        with self.assertRaises(ValueError):
            run_signal_portfolio_backtest(_prices(), SignalPortfolioConfig(method="not_a_method"))

    def test_fallback_days_counted_when_history_thin(self) -> None:
        prices = _prices(start="2024-01-01", end="2024-06-30")
        result = run_signal_portfolio_backtest(
            prices,
            SignalPortfolioConfig(method="mean_variance", top_n=10, max_weight=0.07, estimation_days=60, min_history=5),
        )
        # Candidates appear after only 5 days of history, but covariance
        # estimation needs 20 overlapping rows: early nights fall back.
        self.assertGreater(result["metrics"]["optimizer_fallback_days"], 0)
        self.assertLess(result["metrics"]["optimizer_fallback_share"], 1.0)


if __name__ == "__main__":
    unittest.main()
