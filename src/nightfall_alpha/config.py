from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from nightfall_alpha.paths import CONFIG_DIR, DATA_DIR

ENV_PREFIX = "NIGHTFALL_ALPHA_"


def _load_dotenv(dotenv_path: Path) -> dict[str, str]:
    """Minimal .env reader: KEY=VALUE lines, no shell expansion, real env wins."""
    values: dict[str, str] = {}
    if not dotenv_path.exists():
        return values
    for line in dotenv_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _env(key: str) -> str | None:
    return os.environ.get(key)


@dataclass(frozen=True)
class ProjectSettings:
    name: str = "NightFall Alpha"
    data_dir: Path = DATA_DIR
    seed: int = 42


@dataclass(frozen=True)
class UniverseSettings:
    sample_file: Path = DATA_DIR / "universe" / "sp500_sample.csv"
    live_file: Path = DATA_DIR / "universe" / "sp500_constituents.csv"


@dataclass(frozen=True)
class BacktestSettings:
    initial_capital: float = 1_000_000.0
    fees_bps: float = 0.5
    slippage_bps: float = 1.0


@dataclass(frozen=True)
class StrategySettings:
    lookback_days: int = 63
    min_history: int = 40
    top_n: int = 25
    max_weight: float = 0.07
    min_signal: float = 0.0


@dataclass(frozen=True)
class PortfolioSettings:
    risk_free_rate: float = 0.0
    cvar_alpha: float = 0.95
    max_weight: float = 0.12


@dataclass(frozen=True)
class Settings:
    project: ProjectSettings = ProjectSettings()
    universe: UniverseSettings = UniverseSettings()
    backtest: BacktestSettings = BacktestSettings()
    strategy: StrategySettings = StrategySettings()
    portfolio: PortfolioSettings = PortfolioSettings()


def _path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return Path.cwd() / path


def _section(raw: dict[str, Any], name: str) -> dict[str, Any]:
    value = raw.get(name, {})
    return value if isinstance(value, dict) else {}


def load_settings(path: str | Path | None = None) -> Settings:
    settings_path = Path(path) if path else CONFIG_DIR / "settings.yml"
    if not settings_path.exists():
        return Settings()

    with settings_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}

    project = _section(raw, "project")
    universe = _section(raw, "universe")
    backtest = _section(raw, "backtest")
    strategy = _section(raw, "strategy")
    portfolio = _section(raw, "portfolio")

    dotenv = _load_dotenv(Path.cwd() / ".env")

    def env_value(name: str) -> str | None:
        return _env(f"{ENV_PREFIX}{name}") or dotenv.get(f"{ENV_PREFIX}{name}")

    project_settings = ProjectSettings(
        name=str(project.get("name", ProjectSettings.name)),
        data_dir=_path(env_value("DATA_DIR") or project.get("data_dir", DATA_DIR)),
        seed=int(project.get("seed", ProjectSettings.seed)),
    )

    return Settings(
        project=project_settings,
        universe=UniverseSettings(
            sample_file=_path(universe.get("sample_file", project_settings.data_dir / "universe" / "sp500_sample.csv")),
            live_file=_path(universe.get("live_file", project_settings.data_dir / "universe" / "sp500_constituents.csv")),
        ),
        backtest=BacktestSettings(
            initial_capital=float(env_value("INITIAL_CAPITAL") or backtest.get("initial_capital", BacktestSettings.initial_capital)),
            fees_bps=float(env_value("FEES_BPS") or backtest.get("fees_bps", BacktestSettings.fees_bps)),
            slippage_bps=float(env_value("SLIPPAGE_BPS") or backtest.get("slippage_bps", BacktestSettings.slippage_bps)),
        ),
        strategy=StrategySettings(
            lookback_days=int(strategy.get("lookback_days", StrategySettings.lookback_days)),
            min_history=int(strategy.get("min_history", StrategySettings.min_history)),
            top_n=int(strategy.get("top_n", StrategySettings.top_n)),
            max_weight=float(strategy.get("max_weight", StrategySettings.max_weight)),
            min_signal=float(strategy.get("min_signal", StrategySettings.min_signal)),
        ),
        portfolio=PortfolioSettings(
            risk_free_rate=float(portfolio.get("risk_free_rate", PortfolioSettings.risk_free_rate)),
            cvar_alpha=float(portfolio.get("cvar_alpha", PortfolioSettings.cvar_alpha)),
            max_weight=float(portfolio.get("max_weight", PortfolioSettings.max_weight)),
        ),
    )
