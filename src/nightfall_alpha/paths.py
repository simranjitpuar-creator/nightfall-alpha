from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
REPORTS_DIR = DATA_DIR / "reports"
UNIVERSE_DIR = DATA_DIR / "universe"


def ensure_data_dirs() -> None:
    for path in (RAW_DIR, PROCESSED_DIR, REPORTS_DIR, UNIVERSE_DIR):
        path.mkdir(parents=True, exist_ok=True)
