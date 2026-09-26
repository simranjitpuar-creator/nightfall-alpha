import asyncio
import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scripts.cloud_run_start import seed_data_directory

from nightfall_alpha.config import (
    BacktestSettings,
    PortfolioSettings,
    ProjectSettings,
    Settings,
    StrategySettings,
    UniverseSettings,
    load_settings,
)
from nightfall_alpha.dashboard.app import GuestRateLimiter, _request_requires_write_token, create_app
from nightfall_alpha.data.pipeline import run_research_pipeline


def asgi_request(
    app: object,
    method: str,
    path: str,
    payload: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, object]]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else b""
    received = False
    sent: list[dict[str, object]] = []

    async def receive() -> dict[str, object]:
        nonlocal received
        if received:
            return {"type": "http.disconnect"}
        received = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: dict[str, object]) -> None:
        sent.append(message)

    request_headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode("ascii"))]
    request_headers.extend((key.lower().encode("ascii"), value.encode("utf-8")) for key, value in (headers or {}).items())
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": request_headers,
        "client": ("test-client", 50_000),
        "server": ("test-server", 80),
        "root_path": "",
    }
    asyncio.run(app(scope, receive, send))  # type: ignore[operator]
    start = next(message for message in sent if message["type"] == "http.response.start")
    response_body = b"".join(
        message.get("body", b"") for message in sent if message["type"] == "http.response.body"
    )
    return int(start["status"]), json.loads(response_body or b"{}")


class CloudRunDeploymentTests(unittest.TestCase):
    def test_windows_deploy_script_avoids_native_stderr_merging(self) -> None:
        script = (
            Path(__file__).resolve().parents[1] / "scripts" / "deploy_cloud_run.ps1"
        ).read_text(encoding="utf-8")

        self.assertIn("Get-Command gcloud.cmd", script)
        self.assertIn("function Test-GcloudResource", script)
        self.assertIn("NIGHTFALL_ALPHA_GUEST_DAILY_LIMIT=100", script)
        self.assertIn("[switch]$ReuseExistingWriteToken", script)
        self.assertNotIn("*> $null", script)

    def test_data_dir_override_keeps_universe_files_on_persistent_volume(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings_path = root / "settings.yml"
            settings_path.write_text(
                """
project:
  data_dir: data
universe:
  sample_file: data/universe/sp500_sample.csv
  live_file: data/universe/sp500_constituents.csv
""".strip(),
                encoding="utf-8",
            )
            persistent = root / "persistent-data"
            with patch.dict(os.environ, {"NIGHTFALL_ALPHA_DATA_DIR": str(persistent)}, clear=False):
                settings = load_settings(settings_path)

            self.assertEqual(settings.project.data_dir, persistent)
            self.assertEqual(settings.universe.sample_file, persistent / "universe" / "sp500_sample.csv")
            self.assertEqual(settings.universe.live_file, persistent / "universe" / "sp500_constituents.csv")

    def test_seed_data_directory_never_replaces_persisted_files(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            seed = root / "seed"
            data = root / "data"
            (seed / "universe").mkdir(parents=True)
            (data / "universe").mkdir(parents=True)
            (seed / "universe" / "existing.csv").write_text("seed", encoding="utf-8")
            (seed / "reports").mkdir(parents=True)
            (seed / "reports" / "metrics.json").write_text("{}", encoding="utf-8")
            (data / "universe" / "existing.csv").write_text("persisted", encoding="utf-8")

            copied = seed_data_directory(seed, data)

            self.assertEqual((data / "universe" / "existing.csv").read_text(encoding="utf-8"), "persisted")
            self.assertEqual((data / "reports" / "metrics.json").read_text(encoding="utf-8"), "{}")
            self.assertEqual(copied, [data / "reports" / "metrics.json"])

    def test_write_token_guards_mutations_and_provider_refreshes(self) -> None:
        self.assertFalse(_request_requires_write_token("POST", "/api/run"))
        self.assertFalse(_request_requires_write_token("POST", "/api/portfolio/build"))
        self.assertFalse(_request_requires_write_token("POST", "/api/walkforward"))
        self.assertFalse(_request_requires_write_token("POST", "/api/signal-portfolio/run"))
        self.assertTrue(_request_requires_write_token("POST", "/api/data/download"))
        self.assertTrue(_request_requires_write_token("POST", "/api/era-study/run"))
        self.assertTrue(
            _request_requires_write_token("GET", "/api/benchmarks", {"refresh": "true"})
        )
        self.assertTrue(
            _request_requires_write_token(
                "GET", "/api/universe", {"refresh_market_caps": "true"}
            )
        )
        self.assertFalse(_request_requires_write_token("GET", "/api/overview"))
        self.assertFalse(_request_requires_write_token("GET", "/api/health"))

    def test_guest_rate_limiter_applies_burst_and_daily_caps(self) -> None:
        limiter = GuestRateLimiter(burst_limit=2, burst_window_seconds=10, daily_limit=3)

        self.assertEqual(limiter.allow("client", now=0), (True, 0))
        self.assertEqual(limiter.allow("client", now=1), (True, 0))
        allowed, retry_after = limiter.allow("client", now=2)
        self.assertFalse(allowed)
        self.assertGreaterEqual(retry_after, 1)
        self.assertEqual(limiter.allow("client", now=11), (True, 0))
        allowed, retry_after = limiter.allow("client", now=12)
        self.assertFalse(allowed)
        self.assertGreaterEqual(retry_after, 1)

    def test_guest_backtest_returns_temporary_snapshot_without_changing_saved_run(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            universe_path = root / "universe.csv"
            universe_path.write_text(
                "symbol,name,sector\nAAA,AAA Corp,Technology\nBBB,BBB Corp,Financials\nCCC,CCC Corp,Healthcare\n",
                encoding="utf-8",
            )
            settings = Settings(
                project=ProjectSettings(data_dir=root / "data"),
                universe=UniverseSettings(sample_file=universe_path, live_file=root / "missing.csv"),
                backtest=BacktestSettings(),
                strategy=StrategySettings(lookback_days=20, min_history=10, top_n=3),
                portfolio=PortfolioSettings(),
            )
            run_research_pipeline(
                settings,
                data_source="synthetic",
                symbols_limit=3,
                start="2024-01-01",
                end="2024-06-30",
            )
            metrics_path = settings.project.data_dir / "reports" / "metrics.json"
            saved_metrics = metrics_path.read_bytes()

            with patch.dict(
                os.environ,
                {
                    "NIGHTFALL_ALPHA_WRITE_TOKEN": "test-write-token-123456",
                    "NIGHTFALL_ALPHA_GUEST_MAX_SYMBOLS": "3",
                },
                clear=False,
            ):
                app = create_app(settings)
                status_code, payload = asgi_request(
                    app,
                    "POST",
                    "/api/run",
                    {
                        "price_symbols": "AAA,BBB",
                        "price_start": "2024-02-01",
                        "price_end": "2024-05-31",
                        "lookback_days": 10,
                        "min_history": 5,
                        "top_n": 2,
                    },
                )
                protected_status, _ = asgi_request(app, "POST", "/api/era-study/run")

                self.assertEqual(metrics_path.read_bytes(), saved_metrics)
                admin_status, admin_payload = asgi_request(
                    app,
                    "POST",
                    "/api/run",
                    {"price_symbols": "AAA,BBB", "lookback_days": 10, "min_history": 5, "top_n": 2},
                    {"X-Nightfall-Write-Token": "test-write-token-123456"},
                )

            self.assertEqual(status_code, 200)
            self.assertEqual(payload["mode"], "guest")
            self.assertFalse(payload["persisted"])
            self.assertTrue(payload["dashboard"]["guest"])
            self.assertEqual(payload["guest_limits"]["symbol_count"], 2)
            self.assertEqual(protected_status, 401)
            self.assertEqual(admin_status, 200)
            self.assertEqual(admin_payload["mode"], "admin")
            self.assertTrue(admin_payload["persisted"])


if __name__ == "__main__":
    unittest.main()
