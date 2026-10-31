import unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest

class AppTests(unittest.TestCase):
    def test_demo_and_stale_results(self):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run()
        self.assertFalse(app.exception)
        app.button[0].click().run()
        self.assertEqual(app.metric[0].value, "250.00")
        app.radio[0].set_value("Broken quantity demo").run()
        self.assertEqual(len(app.metric), 0)
        app.button[0].click().run()
        self.assertTrue(app.error)
        self.assertFalse(app.exception)
        self.assertTrue(app.button[1].disabled)

    def test_gemini_reads_streamlit_secrets_and_reports_missing_model(self):
        import os
        from unittest.mock import patch
        with patch.dict(os.environ, {}, clear=True):
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"))
            app.secrets["GEMINI_API_KEY"] = "private-test-key"
            app.run()
            app.radio[0].set_value("Broken quantity demo").run()
            app.button[0].click().run()
            app.checkbox[0].check().run()
            app.button[1].click().run()
            self.assertFalse(app.exception)
            self.assertIn("Missing GEMINI_MODEL", app.warning[0].value)
            self.assertNotIn("private-test-key", app.warning[0].value)
