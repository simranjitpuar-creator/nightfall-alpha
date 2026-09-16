import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd

from nightfall_alpha.backtest.costs import COST_MODELS, CostModel, parse_cost_eras
from nightfall_alpha.backtest.engine import BacktestConfig, run_overnight_backtest
from nightfall_alpha.backtest.walkforward import WalkForwardConfig, run_walk_forward
from nightfall_alpha.data.benchmarks import relative_metrics
from nightfall_alpha.data.membership import apply_membership, load_membership, membership_summary
from nightfall_alpha.data.synthetic import SyntheticMarketConfig, generate_synthetic_ohlcv


def sample_signals() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "signal_date": ["2020-01-02", "2020-01-02", "2020-01-03"],
            "exit_date": ["2020-01-03", "2020-01-03", "2020-01-06"],
            "symbol": ["AAA", "BBB", "AAA"],
            "weight": [0.5, 0.5, 1.0],
            "next_overnight_return": [0.01, -0.02, 0.005],
            "adv_dollars": [20_000_000.0, 10_000_000.0, 20_000_000.0],
        }
    )


def vintage_signals() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "signal_date": ["1990-01-02", "1990-01-03"],
            "exit_date": ["1990-01-03", "1990-01-04"],
            "symbol": ["AAA", "AAA"],
            "weight": [1.0, 1.0],
            "next_overnight_return": [0.01, 0.005],
        }
    )


class TestCostModel(unittest.TestCase):
    def test_flat_mode_ignores_date(self):
        model = CostModel(mode="flat", flat_fees_bps=0.5, flat_slippage_bps=1.0)
        for date in ("1965-01-01", "2005-06-01", "2026-01-01"):
            self.assertAlmostEqual(model.rate_bps(pd.Timestamp(date)), 1.5)

    def test_historical_mode_uses_eras(self):
        model = CostModel(mode="historical")
        self.assertGreater(model.rate_bps(pd.Timestamp("1965-01-01")), model.rate_bps(pd.Timestamp("2020-01-01")))
        self.assertAlmostEqual(model.rate_bps(pd.Timestamp("2020-01-01")), 1.5)

    def test_custom_eras(self):
        eras = parse_cost_eras(
            [
                {"start": "2000-01-01", "fees_bps": 1.0, "slippage_bps": 2.0},
                {"start": "1980-01-01", "fees_bps": 10.0, "slippage_bps": 20.0},
            ]
        )
        self.assertEqual([era.start for era in eras], [pd.Timestamp("1980-01-01"), pd.Timestamp("2000-01-01")])
        model = CostModel(mode="historical", eras=eras)
        self.assertAlmostEqual(model.rate_bps(pd.Timestamp("1990-06-01")), 30.0)
        self.assertAlmostEqual(model.rate_bps(pd.Timestamp("2001-06-01")), 3.0)

    def test_invalid_mode_rejected(self):
        with self.assertRaises(ValueError):
            CostModel(mode="unknown")
        self.assertEqual(COST_MODELS, ("flat", "historical"))


class TestEngineCostsAndCapacity(unittest.TestCase):
    def test_historical_costs_reduce_older_returns_more(self):
        signals = vintage_signals()  # 1990-era: historical era table charges 8+25 bps vs 1.5 flat
        flat = run_overnight_backtest(signals, BacktestConfig(cost_model="flat", fees_bps=0.5, slippage_bps=1.0))
        hist = run_overnight_backtest(signals, BacktestConfig(cost_model="historical"))
        self.assertIn("cost_rate_bps", hist.daily.columns)
        self.assertAlmostEqual(float(hist.daily.iloc[0]["cost_rate_bps"]), 33.0)
        self.assertGreater(float(hist.daily["cost_return"].sum()), float(flat.daily["cost_return"].sum()))

    def test_capital_capacity_caps_deployed_equity(self):
        signals = sample_signals()
        uncapped = run_overnight_backtest(signals, BacktestConfig())
        capped = run_overnight_backtest(
            signals, BacktestConfig(capital_capacity=500_000.0, cash_rate=0.0)
        )
        # With half the capital deployed, day-one PnL is halved.
        day1_uncapped = float(uncapped.daily.iloc[0]["net_return"])
        day1_capped = float(capped.daily.iloc[0]["net_return"])
        self.assertAlmostEqual(day1_capped, day1_uncapped / 2.0, places=9)
        self.assertAlmostEqual(float(capped.daily.iloc[0]["deployed_capital"]), 500_000.0)
        self.assertAlmostEqual(float(capped.daily.iloc[0]["cash_weight"]), 0.5)

    def test_adv_participation_caps_positions(self):
        signals = sample_signals()
        result = run_overnight_backtest(
            signals,
            BacktestConfig(max_adv_participation=0.01),  # 1% of ADV
        )
        day1 = result.trades[result.trades["signal_date"] == pd.Timestamp("2020-01-02")]
        aaa = day1[day1["symbol"] == "AAA"].iloc[0]
        bbb = day1[day1["symbol"] == "BBB"].iloc[0]
        # Uncapped notionals would be $500k each; ADV caps bind below that.
        self.assertAlmostEqual(float(aaa["notional"]), 0.01 * 20_000_000.0, places=2)
        self.assertAlmostEqual(float(bbb["notional"]), 0.01 * 10_000_000.0, places=2)

    def test_cash_rate_rewards_undeployed_capital(self):
        signals = sample_signals().head(2)
        result = run_overnight_backtest(
            signals,
            BacktestConfig(capital_capacity=500_000.0, cash_rate=0.252),
        )
        daily = result.daily.iloc[0]
        expected_cash = 500_000.0 * (0.252 / 252.0)
        deployed_net = 500_000.0 * (0.5 * 0.01 + 0.5 * -0.02 - 2.0 * 1.0 * 1.5 / 10_000.0)
        expected_equity = 1_000_000.0 + deployed_net + expected_cash
        self.assertAlmostEqual(float(daily["ending_equity"]), expected_equity, places=2)


class TestMembership(unittest.TestCase):
    def setUp(self):
        self.prices = pd.DataFrame(
            {
                "date": pd.to_datetime(["2000-01-03", "2010-01-04", "2020-01-02", "2018-06-01"]),
                "symbol": ["OLD", "AAA", "AAA", "NEW"],
                "open": [10.0, 20.0, 25.0, 30.0],
                "high": [10.5, 21.0, 26.0, 31.0],
                "low": [9.5, 19.0, 24.0, 29.0],
                "close": [10.0, 20.0, 25.0, 30.0],
                "volume": [1000.0, 2000.0, 3000.0, 4000.0],
            }
        )

    def test_apply_membership_windows(self):
        membership = pd.DataFrame(
            {
                "symbol": ["AAA", "NEW"],
                "start_date": [pd.Timestamp("2005-01-01"), pd.Timestamp("2018-01-01")],
                "end_date": [pd.NaT, pd.Timestamp("2019-01-01")],
            }
        )
        kept = apply_membership(self.prices, membership)
        self.assertEqual(set(kept["symbol"]), {"AAA", "NEW"})
        # OLD has no membership row; AAA rows before 2005 dropped; NEW kept inside 2018-2019.
        self.assertEqual(len(kept), 3)
        self.assertTrue((kept[kept["symbol"] == "AAA"]["date"] >= pd.Timestamp("2005-01-01")).all())

    def test_load_and_summary(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "membership.csv"
            path.write_text("symbol,start_date,end_date\nAAA,2005-01-01,\n", encoding="utf-8")
            membership = load_membership(path)
        self.assertEqual(list(membership["symbol"]), ["AAA"])
        summary = membership_summary(self.prices, membership)
        self.assertTrue(summary["point_in_time"])
        self.assertIn("OLD", summary["symbols_without_membership"])
        warning = membership_summary(self.prices, None)
        self.assertFalse(warning["point_in_time"])
        self.assertTrue(warning["warning"])

    def test_empty_membership_keeps_prices(self):
        kept = apply_membership(self.prices, pd.DataFrame(columns=["symbol", "start_date", "end_date"]))
        self.assertEqual(len(kept), len(self.prices))


class TestBenchmarkMetrics(unittest.TestCase):
    def test_relative_metrics_basic(self):
        dates = pd.date_range("2020-01-01", periods=300, freq="B")
        benchmark = pd.Series(np.full(300, 0.0004), index=dates)
        strategy = pd.Series(np.full(300, 0.0008), index=dates)  # 2x benchmark, corr 1
        metrics = relative_metrics(strategy, benchmark)
        self.assertAlmostEqual(metrics["beta"], 2.0, places=6)
        self.assertAlmostEqual(metrics["correlation"], 1.0, places=6)
        self.assertGreater(metrics["strategy_total_return"], metrics["benchmark_total_return"])

    def test_duplicate_index_labels_are_tolerated(self):
        dates = pd.date_range("2020-01-01", periods=100, freq="B").append(pd.DatetimeIndex(["2020-01-10"]))
        strategy = pd.Series(np.full(101, 0.001), index=dates)
        benchmark = pd.Series(np.full(101, 0.0005), index=dates)
        metrics = relative_metrics(strategy, benchmark)
        self.assertEqual(metrics["observations"], 100)

    def test_short_overlap_returns_empty(self):
        strategy = pd.Series(np.full(10, 0.001), index=pd.date_range("2020-01-01", periods=10, freq="B"))
        benchmark = pd.Series(np.full(10, 0.001), index=pd.date_range("2020-01-01", periods=10, freq="B"))
        self.assertEqual(relative_metrics(strategy, benchmark), {})


class TestWalkForward(unittest.TestCase):
    def test_walk_forward_produces_oos_only_curve(self):
        prices = generate_synthetic_ohlcv(
            ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"],
            SyntheticMarketConfig(start="2019-01-01", end="2021-12-31", seed=7),
        )
        result = run_walk_forward(
            prices,
            WalkForwardConfig(
                train_days=250,
                test_days=60,
                step_days=60,
                lookback_grid=(42,),
                top_n_grid=(3,),
            ),
            BacktestConfig(initial_capital=100_000.0),
            initial_capital=100_000.0,
        )
        self.assertFalse(result.folds.empty)
        self.assertFalse(result.oos_daily.empty)

        # OOS daily rows must only cover fold test windows and never overlap.
        oos_dates = pd.to_datetime(result.oos_daily["signal_date"])
        self.assertFalse(oos_dates.duplicated().any())
        for _, fold in result.folds.iterrows():
            in_window = (oos_dates >= pd.Timestamp(fold["test_start"])) & (oos_dates <= pd.Timestamp(fold["test_end"]))
            self.assertTrue(in_window.any())

        # Chosen parameters must come from the grid.
        self.assertTrue(set(result.folds["lookback_days"]) <= {42})
        self.assertTrue(set(result.folds["top_n"]) <= {3})

        # Stitched equity must be internally consistent with net returns.
        net = pd.to_numeric(result.oos_daily["net_return"], errors="coerce").fillna(0.0)
        rebuilt = (100_000.0 * (1.0 + net).cumprod()).to_numpy()
        np.testing.assert_allclose(
            pd.to_numeric(result.oos_daily["ending_equity"]).to_numpy(), rebuilt, rtol=1e-9
        )
        self.assertGreater(result.oos_metrics.get("observations", 0), 0)

    def test_walk_forward_rejects_short_history(self):
        prices = generate_synthetic_ohlcv(
            ["AAA", "BBB"], SyntheticMarketConfig(start="2024-01-01", end="2024-03-31", seed=3)
        )
        with self.assertRaises(ValueError):
            run_walk_forward(prices, WalkForwardConfig(train_days=250, test_days=60, step_days=60))


if __name__ == "__main__":
    unittest.main()
