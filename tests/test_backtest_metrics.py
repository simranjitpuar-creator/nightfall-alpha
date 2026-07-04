import math
import unittest

import pandas as pd

from nightfall_alpha.backtest.engine import BacktestConfig, run_overnight_backtest
from nightfall_alpha.backtest.metrics import performance_metrics


class BacktestMetricTests(unittest.TestCase):
    def test_backtest_applies_round_trip_costs(self) -> None:
        signals = pd.DataFrame(
            {
                "signal_date": ["2024-01-02", "2024-01-03"],
                "exit_date": ["2024-01-03", "2024-01-04"],
                "symbol": ["AAA", "AAA"],
                "weight": [1.0, 1.0],
                "next_overnight_return": [0.01, -0.005],
            }
        )
        result = run_overnight_backtest(signals, BacktestConfig(initial_capital=1000.0, fees_bps=1.0, slippage_bps=1.0))

        first_net_return = 0.01 - 2 * ((1.0 + 1.0) / 10000.0)
        self.assertAlmostEqual(result.daily.iloc[0]["net_return"], first_net_return)
        self.assertAlmostEqual(result.daily.iloc[0]["ending_equity"], 1000.0 * (1.0 + first_net_return))
        self.assertEqual(len(result.trades), 2)

    def test_performance_metrics_report_core_fields(self) -> None:
        daily = pd.DataFrame(
            {
                "ending_equity": [101.0, 99.0, 105.0],
                "net_return": [0.01, -0.01980198, 0.06060606],
                "gross_return": [0.011, -0.018, 0.061],
                "cost_return": [0.001, 0.00180198, 0.00039394],
                "gross_exposure": [1.0, 1.0, 1.0],
                "trade_count": [2, 2, 2],
                "round_trip_turnover": [2.0, 2.0, 2.0],
            }
        )
        metrics = performance_metrics(daily, initial_capital=100.0)

        self.assertEqual(metrics["observations"], 3)
        self.assertAlmostEqual(metrics["final_equity"], 105.0)
        self.assertIn("sharpe", metrics)
        self.assertIn("rolling_sharpe_1y", metrics)
        self.assertIsNone(metrics["rolling_sharpe_1y"])
        self.assertLessEqual(metrics["max_drawdown"], 0.0)

    def test_performance_metrics_cagr_uses_elapsed_calendar_years_when_dates_exist(self) -> None:
        daily = pd.DataFrame(
            {
                "signal_date": ["2020-01-01", "2020-07-01"],
                "exit_date": ["2020-07-01", "2021-01-01"],
                "starting_equity": [100.0, 110.0],
                "ending_equity": [110.0, 121.0],
                "net_return": [0.10, 0.10],
                "gross_return": [0.10, 0.10],
                "cost_return": [0.0, 0.0],
                "gross_exposure": [1.0, 1.0],
                "trade_count": [1, 1],
                "round_trip_turnover": [0.0, 0.0],
            }
        )
        metrics = performance_metrics(daily, initial_capital=100.0)
        elapsed_years = 366.0 / 365.25

        self.assertEqual(metrics["start_date"], "2020-01-01")
        self.assertEqual(metrics["end_date"], "2021-01-01")
        self.assertAlmostEqual(metrics["elapsed_years"], elapsed_years)
        self.assertAlmostEqual(metrics["cagr"], 1.21 ** (1.0 / elapsed_years) - 1.0)

    def test_performance_metrics_report_rolling_ratios(self) -> None:
        returns = [
            0.010,
            -0.020,
            0.015,
            -0.005,
            0.018,
            -0.012,
            0.022,
            -0.009,
            0.016,
            -0.018,
            0.024,
            -0.007,
            0.012,
            -0.014,
            0.020,
            -0.010,
            0.017,
            -0.016,
            0.021,
            -0.008,
        ]
        equity = 100.0
        rows = []
        for index, net_return in enumerate(returns):
            starting_equity = equity
            equity *= 1.0 + net_return
            rows.append(
                {
                    "exit_date": pd.Timestamp("2020-01-01") + pd.offsets.BDay(index),
                    "starting_equity": starting_equity,
                    "ending_equity": equity,
                    "net_return": net_return,
                    "gross_return": net_return,
                    "cost_return": 0.0,
                    "gross_exposure": 1.0,
                    "trade_count": 2,
                    "round_trip_turnover": 2.0,
                }
            )
        daily = pd.DataFrame(rows)
        metrics = performance_metrics(daily.sample(frac=1.0, random_state=7), initial_capital=100.0, periods_per_year=4)

        ordered = daily.sort_values("exit_date").reset_index(drop=True)

        def expected(window: pd.DataFrame) -> tuple[float, float, float]:
            window_returns = window["net_return"]
            annualized_excess_return = float(window_returns.mean() * 4)
            annualized_volatility = float(window_returns.std(ddof=0) * math.sqrt(4))
            downside_deviation = float(math.sqrt(float((window_returns.clip(upper=0.0) ** 2).mean())) * math.sqrt(4))
            start_equity = float(window["starting_equity"].iloc[0])
            ending_equity = float(window["ending_equity"].iloc[-1])
            cagr = (ending_equity / start_equity) ** (4 / len(window)) - 1.0
            equity_path = pd.concat(
                [pd.Series([start_equity], dtype=float), window["ending_equity"].reset_index(drop=True)],
                ignore_index=True,
            )
            max_drawdown = float((equity_path / equity_path.cummax() - 1.0).min())
            return (
                annualized_excess_return / annualized_volatility,
                annualized_excess_return / downside_deviation,
                cagr / abs(max_drawdown),
            )

        for horizon, rows_in_window in (("1y", 4), ("3y", 12), ("5y", 20)):
            sharpe, sortino, calmar = expected(ordered.tail(rows_in_window))
            self.assertAlmostEqual(metrics[f"rolling_sharpe_{horizon}"], sharpe)
            self.assertAlmostEqual(metrics[f"rolling_sortino_{horizon}"], sortino)
            self.assertAlmostEqual(metrics[f"rolling_calmar_{horizon}"], calmar)


if __name__ == "__main__":
    unittest.main()
