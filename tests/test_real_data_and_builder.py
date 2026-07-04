import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd

from nightfall_alpha.data.yahoo_provider import _flatten_download
from nightfall_alpha.data.pipeline import load_price_cache, merge_price_history
from nightfall_alpha.data.stooq_provider import stooq_symbol
from nightfall_alpha.data.universe_metadata import SECTOR_ETF_CODES
from nightfall_alpha.portfolio.builder import PortfolioBuildSpec, build_custom_portfolio, parse_symbols


class RealDataAndBuilderTests(unittest.TestCase):
    def test_yahoo_download_normalization_handles_multiindex_tickers(self) -> None:
        dates = pd.bdate_range("2024-01-01", periods=3)
        columns = pd.MultiIndex.from_product(
            [["AAPL", "MSFT"],
             ["Open", "High", "Low", "Close", "Volume"]],
        )
        raw = pd.DataFrame(
            np.array(
                [
                    [100, 101, 99, 100.5, 1000, 200, 202, 198, 201, 2000],
                    [101, 102, 100, 101.5, 1100, 201, 203, 199, 202, 2100],
                    [102, 103, 101, 102.5, 1200, 202, 204, 200, 203, 2200],
                ],
                dtype=float,
            ),
            index=dates,
            columns=columns,
        )

        flat = _flatten_download(raw, ["AAPL", "MSFT"])

        self.assertEqual(set(flat["symbol"]), {"AAPL", "MSFT"})
        self.assertEqual(len(flat), 6)
        self.assertIn("open", flat.columns)
        self.assertIn("close", flat.columns)

    def test_custom_builder_accepts_typed_symbols(self) -> None:
        dates = pd.bdate_range("2024-01-01", periods=90)
        prices = []
        for index, symbol in enumerate(["AAPL", "MSFT", "NVDA", "JPM"]):
            base = 100 + index * 20
            for i, day in enumerate(dates):
                close = base + i * (0.15 + index * 0.03)
                prices.append(
                    {
                        "date": day,
                        "symbol": symbol,
                        "open": close * 0.998,
                        "high": close * 1.01,
                        "low": close * 0.99,
                        "close": close,
                        "volume": 1000,
                    }
                )
        result = build_custom_portfolio(
            pd.DataFrame(prices),
            PortfolioBuildSpec(
                symbols=parse_symbols("AAPL, MSFT NVDA"),
                method="best",
                return_model="close_to_close",
                max_weight=0.6,
                lookback_days=60,
            ),
        )

        self.assertIn(result["selected_portfolio"], set(result["summary"]["portfolio"]))
        self.assertEqual(set(result["symbols"]), {"AAPL", "MSFT", "NVDA"})
        self.assertLessEqual(result["selected_weights"]["weight"].max(), 0.6 + 1e-9)

    def test_merge_price_history_replaces_overlapping_rows(self) -> None:
        existing = pd.DataFrame(
            {
                "date": ["2024-01-02", "2024-01-03"],
                "symbol": ["AAPL", "AAPL"],
                "open": [100.0, 101.0],
                "high": [101.0, 102.0],
                "low": [99.0, 100.0],
                "close": [100.5, 101.5],
                "volume": [1000, 1100],
            }
        )
        incoming = pd.DataFrame(
            {
                "date": ["2024-01-03", "2024-01-04"],
                "symbol": ["AAPL", "MSFT"],
                "open": [111.0, 200.0],
                "high": [112.0, 202.0],
                "low": [110.0, 198.0],
                "close": [111.5, 201.0],
                "volume": [2100, 2000],
            }
        )

        merged = merge_price_history(existing, incoming)

        self.assertEqual(len(merged), 3)
        replaced = merged[(merged["symbol"] == "AAPL") & (merged["date"] == pd.Timestamp("2024-01-03"))].iloc[0]
        self.assertEqual(replaced["open"], 111.0)

    def test_price_cache_repairs_null_and_duplicate_keys(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "prices.csv"
            pd.DataFrame(
                [
                    {
                        "date": "2024-01-02",
                        "symbol": "AAPL",
                        "open": 100.0,
                        "high": 101.0,
                        "low": 99.0,
                        "close": 100.5,
                        "volume": 1000,
                    },
                    {
                        "date": "2024-01-02",
                        "symbol": "AAPL",
                        "open": 111.0,
                        "high": 112.0,
                        "low": 110.0,
                        "close": 111.5,
                        "volume": 2100,
                    },
                    {
                        "date": "",
                        "symbol": "MSFT",
                        "open": 200.0,
                        "high": 201.0,
                        "low": 199.0,
                        "close": 200.5,
                        "volume": 3000,
                    },
                ]
            ).to_csv(path, index=False)

            repaired = load_price_cache(path)

            self.assertEqual(len(repaired), 1)
            self.assertEqual(repaired.iloc[0]["open"], 111.0)
            self.assertEqual(len(pd.read_csv(path)), 1)

    def test_price_cache_skips_malformed_csv_rows(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "prices.csv"
            path.write_text(
                "\n".join(
                    [
                        "date,symbol,open,high,low,close,volume",
                        "2024-01-02,AAPL,100,101,99,100.5,1000",
                        "2024-01-03,AAPL,12024-01-02,AAPL,100,101,99,100.5,1000",
                        "2024-01-03,AAPL,101,102,100,101.5,1100",
                    ]
                ),
                encoding="utf-8",
            )

            repaired = load_price_cache(path)

            self.assertEqual(len(repaired), 2)
            self.assertEqual(repaired["symbol"].tolist(), ["AAPL", "AAPL"])
            self.assertEqual(len(pd.read_csv(path)), 2)

    def test_price_cache_removes_corrupted_future_dates(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "prices.csv"
            pd.DataFrame(
                [
                    {
                        "date": "2024-01-02",
                        "symbol": "AAPL",
                        "open": 100.0,
                        "high": 101.0,
                        "low": 99.0,
                        "close": 100.5,
                        "volume": 1000,
                    },
                    {
                        "date": "7025-03-07",
                        "symbol": "AAPL",
                        "open": 101.0,
                        "high": 102.0,
                        "low": 100.0,
                        "close": 101.5,
                        "volume": 1100,
                    },
                    {
                        "date": "2024-01-03",
                        "symbol": "AAPL",
                        "open": 102.0,
                        "high": 103.0,
                        "low": 101.0,
                        "close": 102.5,
                        "volume": 1200,
                    },
                ]
            ).to_csv(path, index=False)

            repaired = load_price_cache(path)

            self.assertEqual(len(repaired), 2)
            self.assertEqual(repaired["date"].max(), pd.Timestamp("2024-01-03"))
            self.assertEqual(len(pd.read_csv(path)), 2)

    def test_custom_builder_uses_selected_symbol_history_window(self) -> None:
        prices = []
        for day in pd.bdate_range("1962-01-01", periods=20):
            prices.append(
                {
                    "date": day,
                    "symbol": "SPY",
                    "open": 10.0,
                    "high": 10.2,
                    "low": 9.8,
                    "close": 10.1,
                    "volume": 1000,
                }
            )
        for index, symbol in enumerate(["AAPL", "MSFT"]):
            start = "1980-01-01" if symbol == "AAPL" else "1986-01-01"
            periods = 1_800 if symbol == "AAPL" else 90
            for i, day in enumerate(pd.bdate_range(start, periods=periods)):
                close = 100 + index * 20 + i * (0.2 + index * 0.05)
                prices.append(
                    {
                        "date": day,
                        "symbol": symbol,
                        "open": close * 0.998,
                        "high": close * 1.01,
                        "low": close * 0.99,
                        "close": close,
                        "volume": 1000,
                    }
                )

        result = build_custom_portfolio(
            pd.DataFrame(prices),
            PortfolioBuildSpec(
                symbols=("AAPL", "MSFT"),
                method="best",
                return_model="close_to_close",
                max_weight=0.8,
                lookback_days=None,
            ),
        )

        self.assertEqual(result["start_date"], "1986-01-02")
        self.assertEqual(set(result["symbols"]), {"AAPL", "MSFT"})

    def test_custom_builder_does_not_fill_pre_listing_returns_with_zero(self) -> None:
        prices = []
        for symbol, start, periods in (("AAA", "2020-01-01", 360), ("BBB", "2021-01-01", 80)):
            for i, day in enumerate(pd.bdate_range(start, periods=periods)):
                close = 100 + i
                prices.append(
                    {
                        "date": day,
                        "symbol": symbol,
                        "open": close * 0.99,
                        "high": close * 1.01,
                        "low": close * 0.98,
                        "close": close,
                        "volume": 1000,
                    }
                )

        result = build_custom_portfolio(
            pd.DataFrame(prices),
            PortfolioBuildSpec(
                symbols=("AAA", "BBB"),
                method="Mean Variance",
                return_model="close_to_close",
                max_weight=0.8,
                lookback_days=None,
            ),
        )

        self.assertEqual(result["start_date"], "2021-01-04")
        self.assertEqual(result["lookback_days"], 79)

    def test_custom_builder_supports_monthly_rebalancing(self) -> None:
        prices = []
        for index, symbol in enumerate(["AAA", "BBB", "CCC", "DDD"]):
            for i, day in enumerate(pd.bdate_range("2020-01-01", periods=420)):
                close = 100 + index * 15 + i * (0.08 + index * 0.01)
                prices.append(
                    {
                        "date": day,
                        "symbol": symbol,
                        "open": close * (0.998 + index * 0.0001),
                        "high": close * 1.01,
                        "low": close * 0.99,
                        "close": close,
                        "volume": 1000,
                    }
                )

        result = build_custom_portfolio(
            pd.DataFrame(prices),
            PortfolioBuildSpec(
                symbols=("AAA", "BBB", "CCC", "DDD"),
                method="best",
                return_model="close_to_close",
                max_weight=0.4,
                lookback_days=63,
                rebalance_frequency="monthly",
            ),
        )

        self.assertEqual(result["rebalance_frequency"], "monthly")
        self.assertGreater(result["rebalance_count"], 1)
        self.assertIn("rebalance_date", result["weights"].columns)
        self.assertGreater(result["performance_observations"], 0)

    def test_stooq_symbol_adds_us_suffix(self) -> None:
        self.assertEqual(stooq_symbol("AAPL"), "AAPL.US")

    def test_sector_etf_codes_include_core_spdr_sectors(self) -> None:
        self.assertEqual(SECTOR_ETF_CODES["Information Technology"], "XLK")
        self.assertEqual(SECTOR_ETF_CODES["Financials"], "XLF")


if __name__ == "__main__":
    unittest.main()
