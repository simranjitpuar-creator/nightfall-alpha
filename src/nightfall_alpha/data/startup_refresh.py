from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nightfall_alpha.config import Settings
from nightfall_alpha.data.csv_provider import load_universe
from nightfall_alpha.data.pipeline import download_real_market_data, run_research_pipeline
from nightfall_alpha.data.yahoo_provider import fetch_sp500_constituents


_refresh_thread: threading.Thread | None = None
_refresh_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def startup_refresh_status_path(settings: Settings) -> Path:
    reports = settings.project.data_dir / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    return reports / "startup_refresh_status.json"


def read_startup_refresh_status(settings: Settings) -> dict[str, Any]:
    path = startup_refresh_status_path(settings)
    if not path.exists():
        return {"enabled": startup_refresh_enabled(), "status": "idle", "percent": 0}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"enabled": startup_refresh_enabled(), "status": "unknown", "percent": 0}
    data["enabled"] = startup_refresh_enabled()
    return data


def write_startup_refresh_status(settings: Settings, **updates: Any) -> dict[str, Any]:
    current = read_startup_refresh_status(settings)
    current.update(updates)
    startup_refresh_status_path(settings).write_text(json.dumps(current, indent=2, default=str), encoding="utf-8")
    return current


def startup_refresh_enabled() -> bool:
    value = os.environ.get("NIGHTFALL_ALPHA_AUTO_DOWNLOAD", "0").strip().lower()
    return value in {"1", "true", "yes", "on"}


def startup_refresh_options() -> dict[str, Any]:
    limit_raw = os.environ.get("NIGHTFALL_ALPHA_AUTO_SYMBOL_LIMIT", "").strip()
    chunk_raw = os.environ.get("NIGHTFALL_ALPHA_AUTO_CHUNK_SIZE", "50").strip()
    return {
        "source": os.environ.get("NIGHTFALL_ALPHA_AUTO_SOURCE", "yahoo_max").strip() or "yahoo_max",
        "start": os.environ.get("NIGHTFALL_ALPHA_AUTO_START", "1900-01-01").strip() or "1900-01-01",
        "end": os.environ.get("NIGHTFALL_ALPHA_AUTO_END", "").strip() or None,
        "symbols_limit": int(limit_raw) if limit_raw else None,
        "chunk_size": max(1, int(chunk_raw) if chunk_raw else 50),
        "run_backtest": os.environ.get("NIGHTFALL_ALPHA_AUTO_RUN_BACKTEST", "1").strip().lower()
        in {"1", "true", "yes", "on"},
    }


def _load_startup_universe(settings: Settings) -> list[str]:
    try:
        universe = fetch_sp500_constituents()
        settings.universe.live_file.parent.mkdir(parents=True, exist_ok=True)
        universe.to_csv(settings.universe.live_file, index=False)
    except Exception:
        universe_path = settings.universe.live_file if settings.universe.live_file.exists() else settings.universe.sample_file
        universe = load_universe(universe_path)
    return universe["symbol"].dropna().astype(str).drop_duplicates().sort_values().tolist()


def _run_startup_refresh(settings: Settings, options: dict[str, Any]) -> None:
    started_at = _now()
    returned_symbols: list[str] = []
    missing_symbols: list[str] = []
    chunk_errors: list[str] = []
    total_rows = 0
    try:
        symbols = _load_startup_universe(settings)
        if options["symbols_limit"]:
            symbols = symbols[: int(options["symbols_limit"])]
        total_symbols = len(symbols)
        if total_symbols == 0:
            raise ValueError("No symbols were found for the startup market data refresh.")

        write_startup_refresh_status(
            settings,
            status="running",
            stage="downloading",
            percent=2,
            started_at=started_at,
            finished_at=None,
            source=options["source"],
            start=options["start"],
            end=options["end"],
            symbols_total=total_symbols,
            symbols_done=0,
            returned_symbols=0,
            missing_symbols=0,
            chunk_errors=[],
            rows=0,
            error=None,
        )

        chunk_size = int(options["chunk_size"])
        for chunk_start in range(0, total_symbols, chunk_size):
            chunk = symbols[chunk_start : chunk_start + chunk_size]
            chunk_number = chunk_start // chunk_size + 1
            chunk_count = (total_symbols + chunk_size - 1) // chunk_size
            write_startup_refresh_status(
                settings,
                status="running",
                stage=f"downloading chunk {chunk_number} of {chunk_count}",
                symbols_done=chunk_start,
                percent=round(5 + (chunk_start / max(total_symbols, 1)) * 75, 1),
            )
            try:
                result = download_real_market_data(
                    settings,
                    symbols=chunk,
                    start=options["start"],
                    end=options["end"],
                    refresh_universe=False,
                    merge_existing=True,
                    source=options["source"],
                )
                returned_symbols.extend(result.returned_symbols)
                missing_symbols.extend(result.missing_symbols)
                total_rows = len(result.prices)
            except Exception as exc:
                missing_symbols.extend(chunk)
                chunk_errors.append(f"chunk {chunk_number}: {exc}")
            symbols_done = min(chunk_start + len(chunk), total_symbols)
            write_startup_refresh_status(
                settings,
                status="running",
                stage=f"downloaded chunk {chunk_number} of {chunk_count}",
                symbols_done=symbols_done,
                returned_symbols=len(set(returned_symbols)),
                missing_symbols=len(set(missing_symbols)),
                chunk_errors=chunk_errors[-5:],
                rows=total_rows,
                percent=round(5 + (symbols_done / max(total_symbols, 1)) * 75, 1),
            )

        final_symbols = sorted(set(returned_symbols))
        if not final_symbols:
            message = chunk_errors[-1] if chunk_errors else "No symbols returned data during startup refresh."
            raise ValueError(message)
        payload: dict[str, Any] = {
            "status": "complete",
            "stage": "download complete",
            "percent": 100,
            "finished_at": _now(),
            "symbols_done": total_symbols,
            "returned_symbols": len(final_symbols),
            "missing_symbols": len(set(missing_symbols)),
            "chunk_errors": chunk_errors[-5:],
            "rows": total_rows,
        }
        if options["run_backtest"]:
            write_startup_refresh_status(settings, status="running", stage="running signal backtest", percent=90)
            pipeline = run_research_pipeline(
                settings,
                price_start=options["start"],
                price_end=options["end"],
                price_symbols=final_symbols or None,
            )
            payload.update(
                {
                    "stage": "download and backtest complete",
                    "trades": len(pipeline["backtest"].trades),
                    "final_equity": pipeline["metrics"].get("final_equity"),
                    "data_window": pipeline["data_window"],
                }
            )
        write_startup_refresh_status(settings, **payload)
    except Exception as exc:
        write_startup_refresh_status(
            settings,
            status="failed",
            stage="failed",
            percent=100,
            finished_at=_now(),
            error=str(exc),
        )
    finally:
        global _refresh_thread
        with _refresh_lock:
            _refresh_thread = None


def start_startup_refresh(settings: Settings, *, force: bool = False) -> dict[str, Any]:
    global _refresh_thread
    if not force and not startup_refresh_enabled():
        return read_startup_refresh_status(settings)

    with _refresh_lock:
        if _refresh_thread and _refresh_thread.is_alive():
            return read_startup_refresh_status(settings)
        options = startup_refresh_options()
        write_startup_refresh_status(
            settings,
            enabled=startup_refresh_enabled(),
            status="running",
            stage="queued",
            percent=0,
            source=options["source"],
            start=options["start"],
            end=options["end"],
            error=None,
        )
        _refresh_thread = threading.Thread(
            target=_run_startup_refresh,
            args=(settings, options),
            name="nightfall-alpha-startup-refresh",
            daemon=True,
        )
        _refresh_thread.start()
    return read_startup_refresh_status(settings)
