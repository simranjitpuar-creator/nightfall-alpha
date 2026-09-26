import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scripts.cloud_run_start import seed_data_directory

from nightfall_alpha.config import load_settings
from nightfall_alpha.dashboard.app import _request_requires_write_token


class CloudRunDeploymentTests(unittest.TestCase):
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
        self.assertTrue(_request_requires_write_token("POST", "/api/run"))
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


if __name__ == "__main__":
    unittest.main()
