import io
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


def uploaded(name):
    raw = (ROOT / "examples" / "orders" / name).read_bytes()
    upload = io.BytesIO(raw)
    upload.size = len(raw)
    return upload


class AppTests(unittest.TestCase):
    def test_upload_required_on_both_pages(self):
        for path in ("app.py", "pages/2_Investigate.py"):
            with self.subTest(path=path):
                app = AppTest.from_file(str(ROOT / path)).run()
                self.assertFalse(app.exception)
                self.assertEqual(len(app.get("file_uploader")), 1)
                self.assertFalse(app.button or app.selectbox or app.radio or app.metric)

    def test_guided_upload_and_removal(self):
        with patch("streamlit.file_uploader", return_value=uploaded("invalid_quantity.csv")) as uploader:
            app = AppTest.from_file(str(ROOT / "app.py")).run()
            self.assertIsNone(app.selectbox[0].value)
            app.selectbox[0].select("orders").run()
            app.button[0].click().run()
            self.assertEqual(app.session_state["v2_run"].row, 3)
            uploader.return_value = None
            app.run()
            self.assertNotIn("v2_run", app.session_state)
            self.assertFalse(app.button or app.exception)

    def test_quick_check_and_stale_results(self):
        with patch("streamlit.file_uploader", return_value=uploaded("Orders.csv")) as uploader:
            app = AppTest.from_file(str(ROOT / "app.py")).run()
            app.radio[0].set_value("Quick orders check").run()
            app.button[0].click().run()
            self.assertEqual(app.metric[0].value, "222.50")
            uploader.return_value = uploaded("invalid_quantity.csv")
            app.run()
            self.assertFalse(app.metric)
            app.button[0].click().run()
            answers = {item.label: item for item in app.expander}
            self.assertIn("line 3, field: quantity", answers["Which row failed?"].markdown[0].value)
            self.assertFalse(app.exception)
            self.assertTrue(app.button[1].disabled)

    def test_gemini_reads_streamlit_secrets_and_reports_missing_model(self):
        with patch.dict(os.environ, {}, clear=True), patch("streamlit.file_uploader", return_value=uploaded("invalid_quantity.csv")):
            app = AppTest.from_file(str(ROOT / "app.py"))
            app.secrets["GEMINI_API_KEY"] = "private-test-key"
            app.run()
            app.radio[0].set_value("Quick orders check").run()
            app.button[0].click().run()
            app.checkbox[0].check().run()
            app.button[1].click().run()
            self.assertFalse(app.exception)
            self.assertIn("Missing GEMINI_MODEL", app.warning[0].value)
            self.assertNotIn("private-test-key", app.warning[0].value)
