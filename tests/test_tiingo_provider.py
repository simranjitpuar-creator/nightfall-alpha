from __future__ import annotations

import json
import unittest
from unittest.mock import patch

import pandas as pd

from nightfall_alpha.data import pipeline
from nightfall_alpha.data.tiingo_provider import (
    download_tiingo_daily_prices,
    resolve_tiingo_api_key,
)
from nightfall_alpha.data.yahoo_provider import MarketDataProviderError


class _FakeResponse:
    def __init__(self, payload: object):
        self._body = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None


BARS = [
    {
        "date": "2024-01-02T00:00:00.000Z",
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": 100.5,
        "volume": 1_000_000,
        "adjOpen": 99.0,
        "adjHigh": 100.0,
        "adjLow": 98.0,
        "adjClose": 99.5,
        "adjVolume": 1_100_000,
    },
    {
        "date": "2024-01-03T00:00:00.000Z",
        "open": 101.0,
        "high": 102.0,
        "low": 100.0,
        "close": 101.5,
        "volume": 900_000,
        "adjOpen": 100.0,
        "adjHigh": 101.0,
        "adjLow": 99.0,
        "adjClose": 100.5,
        "adjVolume": 990_000,
    },
]


class TiingoProviderTests(unittest.TestCase):
    def test_missing_api_key_raises(self) -> None:
        from pathlib import Path

        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(MarketDataProviderError):
                resolve_tiingo_api_key(dotenv_path=Path("/nonexistent/.env"))

    def test_download_normalizes_adjusted_bars(self) -> None:
        with patch("nightfall_alpha.data.tiingo_provider.urlopen", return_value=_FakeResponse(BARS)):
            result = download_tiingo_daily_prices(["AAPL"], start="2024-01-01", api_key="test-key", pause_seconds=0)
        self.assertEqual(result.returned_symbols, ["AAPL"])
        self.assertEqual(result.missing_symbols, [])
        self.assertEqual(len(result.prices), 2)
        row = result.prices.iloc[0]
        # Adjusted fields must win over raw fields (matches Yahoo auto_adjust).
        self.assertAlmostEqual(row["close"], 99.5)
        self.assertAlmostEqual(row["volume"], 1_100_000)
        self.assertEqual(str(row["date"].date()), "2024-01-02")

    def test_empty_symbol_goes_to_missing(self) -> None:
        with patch("nightfall_alpha.data.tiingo_provider.urlopen", return_value=_FakeResponse([])):
            with self.assertRaises(MarketDataProviderError):
                download_tiingo_daily_prices(["ZZZZ"], start="2024-01-01", api_key="test-key", pause_seconds=0)


class IncrementalDownloadTests(unittest.TestCase):
    def _existing(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "date": pd.to_datetime(["2024-01-04", "2024-01-05", "2024-01-03"]),
                "symbol": ["AAPL", "AAPL", "MSFT"],
                "open": [1.0, 1.0, 1.0],
                "high": [1.0, 1.0, 1.0],
                "low": [1.0, 1.0, 1.0],
                "close": [1.0, 1.0, 1.0],
                "volume": [1.0, 1.0, 1.0],
            }
        )

    def test_incremental_splits_fresh_and_cached(self) -> None:
        calls: list[tuple[list[str], str]] = []

        def fake_download(symbols: list[str], source: str, start: str, end: str | None):
            calls.append((list(symbols), start))
            frame = pd.DataFrame(
                {
                    "date": pd.to_datetime(["2024-01-08"] * len(symbols)),
                    "symbol": symbols,
                    "open": 1.0,
                    "high": 1.0,
                    "low": 1.0,
                    "close": 1.0,
                    "volume": 1.0,
                }
            )
            return pipeline.YahooDownloadResult(
                prices=frame,
                requested_symbols=list(symbols),
                returned_symbols=list(symbols),
                missing_symbols=[],
                start=start,
                end=end,
            )

        with patch.object(pipeline, "_download_from_source", side_effect=fake_download):
            result = pipeline._download_with_optional_incremental(
                "yahoo",
                ["AAPL", "MSFT", "NVDA"],
                "2015-01-01",
                None,
                self._existing(),
                incremental=True,
            )

        self.assertEqual(len(calls), 2)
        fresh_call = next(call for call in calls if "NVDA" in call[0])
        cached_call = next(call for call in calls if "NVDA" not in call[0])
        # Fresh symbols get the full requested start.
        self.assertEqual(fresh_call[1], "2015-01-01")
        # Cached symbols start near the earliest last cached bar (2024-01-03 minus overlap),
        # not at the requested start.
        self.assertEqual(sorted(cached_call[0]), ["AAPL", "MSFT"])
        self.assertGreater(cached_call[1], "2015-01-01")
        self.assertLessEqual(cached_call[1], "2024-01-03")
        self.assertEqual(sorted(result.returned_symbols), ["AAPL", "MSFT", "NVDA"])

    def test_non_incremental_single_call(self) -> None:
        with patch.object(pipeline, "_download_from_source", return_value="sentinel") as mock:
            result = pipeline._download_with_optional_incremental(
                "yahoo", ["AAPL"], "2015-01-01", None, self._existing(), incremental=False
            )
        self.assertEqual(result, "sentinel")
        mock.assert_called_once_with(["AAPL"], "yahoo", "2015-01-01", None)


if __name__ == "__main__":
    unittest.main()
