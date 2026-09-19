from __future__ import annotations

import unittest

import pandas as pd

from nightfall_alpha.research.era_study import era_windows, summarize_era


def _daily_frame(start: str, end: str, gross: float, net: float) -> pd.DataFrame:
    dates = pd.bdate_range(start, end)
    return pd.DataFrame(
        {
            "signal_date": dates,
            "gross_return": gross,
            "net_return": net,
            "trade_count": 10,
        }
    )


class EraWindowsTests(unittest.TestCase):
    def test_windows_clip_to_data_window(self) -> None:
        windows = era_windows(pd.Timestamp("1962-01-02"), pd.Timestamp("2026-09-11"))
        self.assertEqual(len(windows), 7)
        # First era starts at the data floor, not 1900.
        self.assertEqual(windows[0]["start"], pd.Timestamp("1962-01-02"))
        self.assertEqual(windows[0]["end"], pd.Timestamp("1975-04-30"))
        # Last era ends at the data end.
        self.assertEqual(windows[-1]["end"], pd.Timestamp("2026-09-11"))
        self.assertEqual(windows[-1]["name"], "Near-zero commissions")
        # Windows are contiguous.
        for previous, current in zip(windows, windows[1:], strict=False):
            self.assertEqual(current["start"], previous["end"] + pd.Timedelta(days=1))

    def test_windows_skip_eras_outside_data(self) -> None:
        windows = era_windows(pd.Timestamp("2016-01-01"), pd.Timestamp("2020-01-01"))
        self.assertEqual(len(windows), 1)
        self.assertEqual(windows[0]["name"], "Near-zero commissions")


class SummarizeEraTests(unittest.TestCase):
    def test_losing_era_records_survival_milestones(self) -> None:
        daily = _daily_frame("1990-01-01", "1996-12-31", gross=0.001, net=-0.002)
        window = {
            "key": "1990-01-01",
            "name": "Discount brokers",
            "start": pd.Timestamp("1990-01-01"),
            "end": pd.Timestamp("1996-12-31"),
            "fees_bps": 8.0,
            "slippage_bps": 25.0,
            "cost_bps_per_side": 33.0,
        }
        summary = summarize_era(daily, window, 10_000.0)
        self.assertFalse(summary["empty"])
        self.assertLess(summary["net_total_return"], 0)
        self.assertGreater(summary["gross_total_return"], 0)
        self.assertIsNotNone(summary["halved"])
        self.assertIsNotNone(summary["ruined"])
        self.assertEqual(summary["trades"], len(daily) * 10)
        self.assertIn(summary["verdict"], {"wipeout within a year", "capital bleeds out", "slow bleed"})

    def test_winning_era_never_breaches(self) -> None:
        daily = _daily_frame("2015-01-01", "2020-01-01", gross=0.002, net=0.0015)
        window = {
            "key": "2015-01-01",
            "name": "Near-zero commissions",
            "start": pd.Timestamp("2015-01-01"),
            "end": pd.Timestamp("2020-01-01"),
            "fees_bps": 0.5,
            "slippage_bps": 1.0,
            "cost_bps_per_side": 1.5,
        }
        summary = summarize_era(daily, window, 10_000.0)
        self.assertGreater(summary["net_total_return"], 0)
        self.assertIsNone(summary["halved"])
        self.assertIsNone(summary["ruined"])
        self.assertEqual(summary["verdict"], "edge survives costs")
        self.assertGreater(summary["net_sharpe"], 0)

    def test_empty_window_marks_empty(self) -> None:
        daily = _daily_frame("2020-01-01", "2021-01-01", gross=0.001, net=0.001)
        window = {
            "key": "1900-01-01",
            "name": "Fixed commissions & wide spreads",
            "start": pd.Timestamp("1962-01-01"),
            "end": pd.Timestamp("1975-04-30"),
            "fees_bps": 30.0,
            "slippage_bps": 60.0,
            "cost_bps_per_side": 90.0,
        }
        summary = summarize_era(daily, window, 10_000.0)
        self.assertTrue(summary["empty"])
        self.assertEqual(summary["days"], 0)


if __name__ == "__main__":
    unittest.main()
