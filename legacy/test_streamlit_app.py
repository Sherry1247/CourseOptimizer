from pathlib import Path
import unittest


try:
    from streamlit.testing.v1 import AppTest
except ImportError:  # Core planner tests remain runnable without UI dependencies.
    AppTest = None


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipIf(AppTest is None, "Streamlit is not installed")
class StreamlitSmokeTest(unittest.TestCase):
    def test_app_renders_without_exception(self):
        app = AppTest.from_file(str(ROOT / "src" / "streamlit_app.py"))
        app.run(timeout=20)
        self.assertEqual([], list(app.exception))
        self.assertEqual("🦡 BadgerPlan", app.title[0].value)


if __name__ == "__main__":
    unittest.main()
