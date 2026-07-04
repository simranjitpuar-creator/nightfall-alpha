import unittest

import pandas as pd

from nightfall_alpha.data.synthetic import SyntheticMarketConfig, generate_synthetic_ohlcv
from nightfall_alpha.strategy.overnight import OvernightEffectConfig, build_overnight_features, generate_signals


class OvernightStrategyTests(unittest.TestCase):
    def test_features_use_next_overnight_return_as_realized_trade_return(self) -> None:
        prices = pd.DataFrame(
            {
                "date": pd.bdate_range("2024-01-01", periods=4).repeat(1),
                "symbol": ["AAA"] * 4,
                "open": [100.0, 102.0, 101.0, 104.0],
                "high": [101.0, 103.0, 102.0, 105.0],
                "low": [99.0, 101.0, 100.0, 103.0],
                "close": [101.0, 100.0, 103.0, 105.0],
                "volume": [1000, 1000, 1000, 1000],
            }
        )

        features = build_overnight_features(prices, lookback_days=2, min_history=1)
        first_day = features[features["date"] == pd.Timestamp("2024-01-01")].iloc[0]
        second_day = features[features["date"] == pd.Timestamp("2024-01-02")].iloc[0]

        self.assertAlmostEqual(second_day["overnight_return"], 102.0 / 101.0 - 1.0)
        self.assertAlmostEqual(first_day["next_overnight_return"], second_day["overnight_return"])

    def test_generated_signals_respect_weight_cap(self) -> None:
        prices = generate_synthetic_ohlcv(
            ["AAA", "BBB", "CCC", "DDD", "EEE"],
            SyntheticMarketConfig(start="2022-01-01", end="2022-06-30", seed=7),
        )
        signals = generate_signals(
            prices,
            OvernightEffectConfig(lookback_days=10, min_history=5, top_n=3, max_weight=0.4, min_signal=-10.0),
        )

        self.assertFalse(signals.empty)
        self.assertLessEqual(signals["weight"].max(), 0.4 + 1e-9)
        daily_weight_sums = signals.groupby("signal_date")["weight"].sum()
        self.assertTrue((daily_weight_sums <= 1.0 + 1e-9).all())


if __name__ == "__main__":
    unittest.main()
