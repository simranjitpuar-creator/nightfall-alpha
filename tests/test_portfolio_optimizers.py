import unittest

import numpy as np
import pandas as pd

from nightfall_alpha.portfolio.optimizers import (
    OptimizerSuiteSettings,
    build_portfolio_suite,
    build_rebalanced_portfolio_suite,
    project_capped_simplex,
)
from nightfall_alpha.portfolio.risk import prepare_optimization_matrix


class PortfolioOptimizerTests(unittest.TestCase):
    def test_capped_simplex_projects_to_feasible_long_only_weights(self) -> None:
        weights = project_capped_simplex([4.0, 1.0, -2.0, 0.5], max_weight=0.45)

        self.assertAlmostEqual(weights.sum(), 1.0)
        self.assertTrue((weights >= 0.0).all())
        self.assertTrue((weights <= 0.45 + 1e-9).all())

    def test_portfolio_suite_returns_expected_styles(self) -> None:
        rng = np.random.default_rng(123)
        returns = pd.DataFrame(
            rng.normal(0.0002, 0.01, size=(1300, 6)),
            index=pd.bdate_range("2019-01-02", periods=1300),
            columns=["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"],
        )
        summary, weights = build_portfolio_suite(returns, max_weight=0.35, initial_capital=250_000.0)

        self.assertGreaterEqual(len(summary), 6)
        self.assertFalse(weights.empty)
        self.assertLessEqual(weights["weight"].max(), 0.35 + 1e-9)
        self.assertIn("Black-Litterman", set(summary["portfolio"]))
        required_metrics = {
            "initial_capital",
            "final_equity",
            "total_return",
            "cagr",
            "start_date",
            "end_date",
            "elapsed_years",
            "observations",
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
            "win_rate",
            "profit_factor",
            "weight_sum",
            "gross_exposure",
            "cash_weight",
            "max_weight_limit",
            "optimizer_parameters",
            "rebalance_frequency",
            "rebalance_count",
            "average_turnover",
            "var_95",
            "cvar_95",
            "positions",
        }
        self.assertTrue(required_metrics.issubset(set(summary.columns)))

        first = summary.iloc[0]
        self.assertAlmostEqual(float(first["initial_capital"]), 250_000.0)
        self.assertAlmostEqual(float(first["final_equity"]), 250_000.0 * (1.0 + float(first["total_return"])))
        self.assertEqual(first["start_date"], "2019-01-02")
        self.assertEqual(first["end_date"], str(returns.index[-1].date()))
        self.assertGreater(float(first["elapsed_years"]), 4.0)
        expected_cagr = (float(first["final_equity"]) / float(first["initial_capital"])) ** (
            1.0 / float(first["elapsed_years"])
        ) - 1.0
        self.assertAlmostEqual(float(first["cagr"]), expected_cagr)
        for column in required_metrics - {"profit_factor"}:
            self.assertFalse(pd.isna(first[column]), column)

    def test_short_portfolio_window_blanks_cagr_and_calmar(self) -> None:
        rng = np.random.default_rng(456)
        returns = pd.DataFrame(
            rng.normal(0.002, 0.01, size=(40, 4)),
            columns=["AAA", "BBB", "CCC", "DDD"],
        )
        summary, _ = build_portfolio_suite(returns, max_weight=0.4, initial_capital=10_000.0)

        first = summary.iloc[0]
        self.assertEqual(int(first["observations"]), 40)
        self.assertAlmostEqual(float(first["final_equity"]), 10_000.0 * (1.0 + float(first["total_return"])))
        self.assertTrue(pd.isna(first["cagr"]))
        self.assertTrue(pd.isna(first["calmar"]))

    def test_prepare_optimization_matrix_filters_thin_history_universe_symbols(self) -> None:
        dates = pd.bdate_range("2020-01-01", periods=100)
        matrix = pd.DataFrame(index=dates)
        for index in range(8):
            matrix[f"FULL{index}"] = 0.001 + index * 0.00001
        matrix["THIN1"] = np.nan
        matrix["THIN2"] = np.nan
        matrix.loc[dates[-10:], "THIN1"] = 0.01
        matrix.loc[dates[-8:], "THIN2"] = -0.01

        prepared, metadata = prepare_optimization_matrix(matrix, allow_symbol_filtering=True)

        self.assertEqual(prepared.shape, (100, 8))
        self.assertNotIn("THIN1", prepared.columns)
        self.assertNotIn("THIN2", prepared.columns)
        self.assertEqual(set(metadata["excluded_symbols"]), {"THIN1", "THIN2"})

    def test_portfolio_suite_allows_low_max_weight_with_cash_balance(self) -> None:
        returns = pd.DataFrame(
            np.random.default_rng(789).normal(0.001, 0.01, size=(90, 3)),
            index=pd.bdate_range("2024-01-01", periods=90),
            columns=["AAA", "BBB", "CCC"],
        )

        summary, weights = build_portfolio_suite(returns, max_weight=0.01)

        self.assertFalse(summary.empty)
        self.assertFalse(weights.empty)
        self.assertLessEqual(weights["weight"].max(), 0.01 + 1e-9)
        self.assertTrue((summary["weight_sum"] <= 0.03 + 1e-9).all())
        self.assertTrue((summary["cash_weight"] >= 0.97 - 1e-9).all())

    def test_portfolio_suite_applies_transaction_cost_drag(self) -> None:
        returns = pd.DataFrame(
            np.full((60, 4), 0.001),
            index=pd.bdate_range("2024-01-01", periods=60),
            columns=["AAA", "BBB", "CCC", "DDD"],
        )

        free_summary, _ = build_portfolio_suite(
            returns,
            max_weight=0.25,
            initial_capital=100_000.0,
            fees_bps=0.0,
            slippage_bps=0.0,
        )
        cost_summary, _ = build_portfolio_suite(
            returns,
            max_weight=0.25,
            initial_capital=100_000.0,
            fees_bps=5.0,
            slippage_bps=5.0,
        )

        free_row = free_summary.set_index("portfolio").loc["Inverse Volatility"]
        cost_row = cost_summary.set_index("portfolio").loc["Inverse Volatility"]
        self.assertGreater(float(cost_row["total_cost_return"]), 0.0)
        self.assertLess(float(cost_row["final_equity"]), float(free_row["final_equity"]))

    def test_portfolio_suite_accepts_method_specific_parameters(self) -> None:
        returns = pd.DataFrame(
            np.random.default_rng(987).normal(0.001, 0.015, size=(260, 5)),
            index=pd.bdate_range("2023-01-02", periods=260),
            columns=["AAA", "BBB", "CCC", "DDD", "EEE"],
        )

        summary, weights = build_portfolio_suite(
            returns,
            max_weight=0.2,
            optimizer_settings=OptimizerSuiteSettings(
                default_max_weight=0.2,
                kelly_fraction=0.25,
                kelly_max_weight=0.05,
                mean_variance_risk_aversion=12.0,
                cvar_alpha=0.9,
                black_litterman_tau=0.08,
                black_litterman_max_weight=0.04,
            ),
        )

        caps = summary.set_index("portfolio")["max_weight_limit"]
        self.assertAlmostEqual(float(caps["Kelly 50%"]), 0.05)
        self.assertAlmostEqual(float(caps["Mean Variance"]), 0.2)
        self.assertAlmostEqual(float(caps["Black-Litterman"]), 0.04)
        self.assertTrue((weights[weights["portfolio"] == "Kelly 50%"]["weight"] <= 0.05 + 1e-9).all())
        self.assertTrue((weights[weights["portfolio"] == "Black-Litterman"]["weight"] <= 0.04 + 1e-9).all())
        params = summary.set_index("portfolio")["optimizer_parameters"]
        self.assertIn("fraction=0.25", params["Kelly 50%"])
        self.assertIn("alpha=0.9", params["CVaR Aware"])

    def test_rebalanced_portfolio_suite_returns_snapshots_and_metrics(self) -> None:
        returns = pd.DataFrame(
            np.random.default_rng(654).normal(0.0005, 0.012, size=(520, 6)),
            index=pd.bdate_range("2022-01-03", periods=520),
            columns=["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"],
        )

        summary, weights = build_rebalanced_portfolio_suite(
            returns,
            rebalance_frequency="monthly",
            lookback_days=63,
            max_weight=0.3,
            initial_capital=50_000.0,
        )

        self.assertFalse(summary.empty)
        self.assertFalse(weights.empty)
        self.assertIn("rebalance_date", weights.columns)
        self.assertTrue((summary["rebalance_frequency"] == "monthly").all())
        self.assertTrue((summary["rebalance_count"] > 1).all())
        self.assertGreater(pd.to_datetime(summary["start_date"]).min(), returns.index[0])
        self.assertLessEqual(weights["weight"].max(), 0.3 + 1e-9)
        self.assertGreater(weights["rebalance_date"].nunique(), 1)


if __name__ == "__main__":
    unittest.main()
