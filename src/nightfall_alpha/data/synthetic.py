from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from nightfall_alpha.data.schema import PRICE_COLUMNS, validate_prices_frame


@dataclass(frozen=True)
class SyntheticMarketConfig:
    start: str = "2018-01-01"
    end: str = "2025-12-31"
    seed: int = 42
    start_price_min: float = 35.0
    start_price_max: float = 350.0
    base_volume_min: int = 850_000
    base_volume_max: int = 12_000_000


def generate_synthetic_ohlcv(
    symbols: Sequence[str],
    config: SyntheticMarketConfig | None = None,
) -> pd.DataFrame:
    cfg = config or SyntheticMarketConfig()
    rng = np.random.default_rng(cfg.seed)
    dates = pd.bdate_range(cfg.start, cfg.end)
    frames: list[pd.DataFrame] = []

    for symbol_index, symbol in enumerate(symbols):
        symbol_rng = np.random.default_rng(cfg.seed + symbol_index * 7919)
        start_price = symbol_rng.uniform(cfg.start_price_min, cfg.start_price_max)
        base_volume = int(symbol_rng.integers(cfg.base_volume_min, cfg.base_volume_max))

        overnight_mu = symbol_rng.normal(0.00010, 0.00010)
        intraday_mu = symbol_rng.normal(-0.00001, 0.00007)
        overnight_vol = symbol_rng.uniform(0.0045, 0.0110)
        intraday_vol = symbol_rng.uniform(0.0075, 0.0175)
        beta = symbol_rng.uniform(0.65, 1.35)

        market_overnight = rng.normal(0.00005, 0.0045, len(dates))
        market_intraday = rng.normal(0.00000, 0.0060, len(dates))
        idio_overnight = symbol_rng.normal(overnight_mu, overnight_vol, len(dates))
        idio_intraday = symbol_rng.normal(intraday_mu, intraday_vol, len(dates))

        overnight_log_returns = beta * market_overnight + idio_overnight
        intraday_log_returns = beta * market_intraday + idio_intraday

        open_prices = np.empty(len(dates))
        close_prices = np.empty(len(dates))
        high_prices = np.empty(len(dates))
        low_prices = np.empty(len(dates))
        volumes = np.empty(len(dates), dtype=np.int64)

        previous_close = start_price
        for i in range(len(dates)):
            open_price = previous_close * np.exp(overnight_log_returns[i])
            close_price = open_price * np.exp(intraday_log_returns[i])
            spread = abs(symbol_rng.normal(0.006, 0.004))
            high_price = max(open_price, close_price) * (1.0 + spread)
            low_price = min(open_price, close_price) * max(0.01, 1.0 - spread)
            volume_noise = symbol_rng.lognormal(mean=0.0, sigma=0.35)

            open_prices[i] = open_price
            close_prices[i] = close_price
            high_prices[i] = high_price
            low_prices[i] = low_price
            volumes[i] = max(1, int(base_volume * volume_noise))
            previous_close = close_price

        frames.append(
            pd.DataFrame(
                {
                    "date": dates,
                    "symbol": symbol,
                    "open": open_prices.round(4),
                    "high": high_prices.round(4),
                    "low": low_prices.round(4),
                    "close": close_prices.round(4),
                    "volume": volumes,
                }
            )
        )

    if not frames:
        return pd.DataFrame(columns=PRICE_COLUMNS)

    return validate_prices_frame(pd.concat(frames, ignore_index=True))
