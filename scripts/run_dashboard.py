from __future__ import annotations

import argparse
import sys
from pathlib import Path

import uvicorn


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nightfall_alpha.dashboard.app import create_app  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the NightFall Alpha dashboard.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8776)
    args = parser.parse_args()

    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
