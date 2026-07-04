from __future__ import annotations

from pathlib import Path

import pandas as pd

from nightfall_alpha.data.schema import normalize_symbol, validate_prices_frame


def load_universe(path: str | Path) -> pd.DataFrame:
    universe_path = Path(path)
    if not universe_path.exists():
        raise FileNotFoundError(f"Universe file not found: {universe_path}")

    universe = pd.read_csv(universe_path)
    if "symbol" not in universe.columns:
        raise ValueError(f"Universe file must contain a symbol column: {universe_path}")

    universe = universe.copy()
    universe["symbol"] = universe["symbol"].map(normalize_symbol)
    return universe.drop_duplicates("symbol").reset_index(drop=True)


def load_price_file(path: str | Path) -> pd.DataFrame:
    price_path = Path(path)
    if not price_path.exists():
        raise FileNotFoundError(f"Price file not found: {price_path}")
    return validate_prices_frame(pd.read_csv(price_path))


def save_price_file(prices: pd.DataFrame, path: str | Path) -> None:
    price_path = Path(path)
    price_path.parent.mkdir(parents=True, exist_ok=True)
    validate_prices_frame(prices).to_csv(price_path, index=False)
