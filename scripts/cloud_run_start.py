"""Seed an empty persistent data volume, then start the Cloud Run service."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

DEFAULT_DATA_DIR = Path("/var/lib/nightfall-alpha")
DEFAULT_SEED_DIR = Path("/app/seed-data")


def seed_data_directory(seed_dir: Path, data_dir: Path) -> list[Path]:
    """Copy packaged baseline artifacts into an empty/new persistent volume.

    Existing files are never replaced. This makes new deployments immediately
    usable while preserving market data and reports from previous revisions.
    """

    copied: list[Path] = []
    data_dir.mkdir(parents=True, exist_ok=True)
    if not seed_dir.exists():
        return copied

    for source in sorted(path for path in seed_dir.rglob("*") if path.is_file()):
        relative = source.relative_to(seed_dir)
        target = data_dir / relative
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        copied.append(target)
    return copied


def main() -> None:
    data_dir = Path(os.environ.get("NIGHTFALL_ALPHA_DATA_DIR", DEFAULT_DATA_DIR))
    seed_dir = Path(os.environ.get("NIGHTFALL_ALPHA_SEED_DATA_DIR", DEFAULT_SEED_DIR))
    copied = seed_data_directory(seed_dir, data_dir)
    if copied:
        print(f"Seeded {len(copied)} baseline data files in {data_dir}", flush=True)

    port = os.environ.get("PORT", "8080")
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "nightfall_alpha.dashboard.app:create_app",
        "--factory",
        "--host",
        "0.0.0.0",
        "--port",
        port,
        "--workers",
        "1",
        "--proxy-headers",
        "--forwarded-allow-ips=*",
    ]
    os.execv(sys.executable, command)


if __name__ == "__main__":
    main()
