import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest


class StreamlitAppTests(unittest.TestCase):
    def test_default_page_renders_without_exceptions(self) -> None:
        app_path = Path(__file__).resolve().parents[1] / "streamlit_app.py"
        app = AppTest.from_file(app_path).run(timeout=120)

        self.assertEqual([exception.value for exception in app.exception], [])
        self.assertEqual(app.sidebar.radio[0].value, "Signal Backtest")


if __name__ == "__main__":
    unittest.main()
