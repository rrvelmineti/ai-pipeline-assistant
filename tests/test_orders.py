import io
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from orders_assistant.core import analyze, MAX_BYTES
from orders_assistant.explain import explain, gemini_explain, ExplanationError
from orders_assistant.storage import save_json, save_run, history

ROOT = Path(__file__).resolve().parents[1]

class OrdersTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.csv = self.folder / "Orders.csv"

    def run_csv(self, data):
        self.csv.write_bytes(data.encode("utf-8") if isinstance(data, str) else data)
        return analyze(self.csv)

    def test_decimal_success(self):
        r = self.run_csv("quantity,unit_price\n3,0.10\n2,1.25\n")
        self.assertEqual((r["status"], r["total_sales"], r["rows_processed"]), ("success", "2.80", 2))

    def test_failure_no_partial_total(self):
        r = self.run_csv("quantity,unit_price\n2,30\nthree,30\n4,25")
        self.assertEqual((r["error"]["code"], r["error"]["row"]), ("invalid_quantity", 3))
        self.assertIsNone(r["total_sales"])
        self.assertIsNone(explain(r)["underlying_cause"])

    def test_invalid_numbers(self):
        for quantity in ["0", "-1", "1.2", "NaN", "", "1000001", "1e2"]:
            with self.subTest(quantity=quantity):
                self.assertEqual(self.run_csv(f"quantity,unit_price\n{quantity},30")["error"]["code"], "invalid_quantity")
        for price in ["-1", "NaN", "inf", "1e2", "", "1.001", "1000001"]:
            with self.subTest(price=price):
                self.assertEqual(self.run_csv(f"quantity,unit_price\n1,{price}")["error"]["code"], "invalid_price")

    def test_input_failures(self):
        for data, code in [(b"\xff", "invalid_csv"), (b"", "invalid_headers"),
                           (b"quantity,quantity\n1,2", "invalid_headers"),
                           (b"quantity,unit_price\n", "empty_orders"),
                           (b"quantity,unit_price\n1,2,3", "invalid_row"),
                           (b'quantity,unit_price\n1,"oops', "invalid_csv")]:
            with self.subTest(code=code):
                self.assertEqual(self.run_csv(data)["error"]["code"], code)
        self.assertEqual(analyze(self.folder / "missing.csv")["error"]["code"], "input_unreadable")

    def test_limits(self):
        self.assertEqual(self.run_csv(b"x" * (MAX_BYTES + 1))["error"]["code"], "input_too_large")
        self.assertEqual(self.run_csv("quantity,unit_price\n" + "1,1\n" * 10001)["error"]["code"], "too_many_rows")

    def test_bom_reordered_headers_zero_price(self):
        self.assertEqual(self.run_csv("\ufeffunit_price,quantity\n0, 2 \n30.25,3")["total_sales"], "90.75")

    def test_snapshot_and_history(self):
        path, db = self.folder / "latest.json", self.folder / "runs.db"
        for data in ["quantity,unit_price\nthree,30", "quantity,unit_price\n2,30"]:
            r = self.run_csv(data)
            save_run(r, db)
            save_json(r, path)
        self.assertEqual(json.loads(path.read_text())["status"], "success")
        self.assertEqual(len(history(db)), 2)
        self.assertEqual(history(self.folder / "missing.db"), [])

    def test_cli_from_another_directory(self):
        self.run_csv("quantity,unit_price\n2,30\n3,30\n4,25")
        def cli(*args):
            return subprocess.run([sys.executable, "-m", "orders_assistant", *args], cwd=self.folder,
                env=dict(os.environ, PYTHONPATH=str(ROOT)), capture_output=True, text=True, timeout=10)
        r = cli("run", str(self.csv))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["total_sales"], "250.00")
        self.assertEqual(cli("explain").returncode, 0)
        self.assertEqual(len(json.loads(cli("history").stdout)), 1)
        self.run_csv("quantity,unit_price\nthree,30")
        self.assertEqual(cli("run", str(self.csv)).returncode, 1)
        self.assertEqual(json.loads(cli("explain").stdout)["stage"], "validation")
        self.assertEqual(cli("explain", "missing.json").returncode, 2)
        self.assertEqual(cli("run", str(self.csv), "--output", str(self.csv)).returncode, 2)
        self.assertEqual(self.csv.read_text(), "quantity,unit_price\nthree,30")

    def test_gemini_classification(self):
        r = self.run_csv("quantity,unit_price\nSECRET,30")
        expected = {"code": "invalid_quantity", "stage": "validation", "underlying_cause": None}
        def opener(request, timeout):
            self.assertNotIn("SECRET", request.data.decode())
            self.assertEqual(timeout, 30)
            return io.BytesIO(json.dumps({"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(expected)}]}}]}).encode())
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key", "GEMINI_MODEL": "test-model"}):
            self.assertEqual(gemini_explain(r, opener)["source"], "gemini-verified classification")

    def test_gemini_rejects_unproven_cause(self):
        r = self.run_csv("quantity,unit_price\nthree,30")
        for value in [None, {}, {"code": "invalid_quantity", "stage": "validation", "underlying_cause": "outage"}]:
            payload = {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(value)}]}}]}
            with self.subTest(value=value), patch.dict(os.environ, {"GEMINI_API_KEY": "test", "GEMINI_MODEL": "test"}):
                with self.assertRaises(ExplanationError):
                    gemini_explain(r, lambda *a, **k: io.BytesIO(json.dumps(payload).encode()))
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(ExplanationError):
            gemini_explain(r)

    def test_gemini_timeout(self):
        r = self.run_csv("quantity,unit_price\nthree,30")
        def timeout(*a, **k):
            raise TimeoutError()
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test", "GEMINI_MODEL": "test"}):
            with self.assertRaises(ExplanationError):
                gemini_explain(r, timeout)

    def test_unknown_record_rejected(self):
        for r in [{}, {"schema_version": 1, "status": "error", "error": {"code": "invented"}}]:
            with self.assertRaises(ExplanationError):
                explain(r)

    def test_malformed_provider_payloads(self):
        r = self.run_csv("quantity,unit_price\nthree,30")
        for payload in [{"candidates": [None]}, {"candidates": []}, {"candidates": [{"finishReason": "MAX_TOKENS"}]}]:
            with self.subTest(payload=payload), patch.dict(os.environ, {"GEMINI_API_KEY": "test", "GEMINI_MODEL": "test"}):
                with self.assertRaises(ExplanationError):
                    gemini_explain(r, lambda *a, **k: io.BytesIO(json.dumps(payload).encode()))

    def test_http_error_does_not_leak_provider_body(self):
        import urllib.error
        r = self.run_csv("quantity,unit_price\nthree,30")
        def fail(*a, **k):
            raise urllib.error.HTTPError("https://example.test", 429, "SECRET", {}, None)
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test", "GEMINI_MODEL": "test"}):
            with self.assertRaises(ExplanationError) as caught:
                gemini_explain(r, fail)
        self.assertIn("429", str(caught.exception))
        self.assertNotIn("SECRET", str(caught.exception))

    def test_database_connections_are_closed(self):
        from unittest.mock import MagicMock
        connection = MagicMock()
        connection.execute.return_value = []
        record = self.run_csv("quantity,unit_price\n2,30")
        db = self.folder / "close-test.db"
        db.touch()
        with patch("orders_assistant.storage.sqlite3.connect", return_value=connection):
            save_run(record, db)
            self.assertEqual(connection.close.call_count, 1)
            history(db)
            self.assertEqual(connection.close.call_count, 2)
