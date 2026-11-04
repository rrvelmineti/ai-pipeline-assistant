import io
import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


def uploaded(raw):
    upload = io.BytesIO(raw)
    upload.size = len(raw)
    return upload


class AppTests(unittest.TestCase):
    def test_upload_required_on_both_pages(self):
        for path in ("app.py", "pages/2_Investigate.py"):
            app = AppTest.from_file(str(ROOT / path)).run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.get("file_uploader")), 1)
            self.assertFalse(app.button or app.selectbox or app.radio or app.metric)

    def test_all_issues_and_upload_removal(self):
        with patch("streamlit.file_uploader", return_value=uploaded(b"quantity,price\nthree,bad\n2.5,wrong")) as uploader:
            app = AppTest.from_file(str(ROOT / "app.py")).run()
            self.assertEqual(app.selectbox[0].value, "Whole number")
            self.assertFalse(app.number_input)
            app.button[0].click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state["csv_report"].issue_count, 4)
            self.assertEqual(app.dataframe[0].value.iloc[0]["entered"], "three")
            self.assertTrue(app.button[1].disabled)
            uploader.return_value = None
            app.run()
            self.assertNotIn("csv_report", app.session_state)
            self.assertFalse(app.metric or app.exception)

    def test_no_totals_and_no_stale_rule_or_file_results(self):
        with patch("streamlit.file_uploader", return_value=uploaded(b"amount\n12.34")) as uploader:
            app = AppTest.from_file(str(ROOT / "app.py")).run()
            app.button[0].click().run()
            self.assertTrue(app.success)
            self.assertEqual([m.label for m in app.metric], ["Records reviewed", "Issues found"])
            app.selectbox[0].select("Whole number").run()
            self.assertNotIn("csv_report", app.session_state)
            app.button[0].click().run()
            self.assertEqual(app.session_state["csv_report"].issue_count, 1)
            uploader.return_value = uploaded(b"amount\n12")
            app.run()
            self.assertFalse(app.metric)
            self.assertEqual(app.selectbox[0].value, "Number")
            self.assertFalse(app.exception)

    def test_ambiguous_date_requires_choice(self):
        with patch("streamlit.file_uploader", return_value=uploaded(b"date\n03/04/2026")):
            app = AppTest.from_file(str(ROOT / "app.py")).run()
            self.assertTrue(app.button[0].disabled)
            app.selectbox[1].select("DD/MM/YYYY").run()
            app.button[0].click().run()
            self.assertTrue(app.success)
            self.assertFalse(app.exception)

    def test_direct_investigate_route(self):
        with patch("streamlit.file_uploader", return_value=uploaded(b"name,date\n123,2026-02-30")):
            app = AppTest.from_file(str(ROOT / "pages/2_Investigate.py")).run()
            app.selectbox[2].select("YYYY-MM-DD").run()
            app.button[0].click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state["csv_report"].issue_count, 2)
