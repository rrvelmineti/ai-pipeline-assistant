import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import Mock, patch

from langchain_core.documents import Document
from streamlit.testing.v1 import AppTest
from orders_assistant.investigate import Index, Citation, Choice, context, corpus, investigate
from orders_assistant.pipeline_v2 import ScanReport, process, stored_count


class V2Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "orders.db"
        self.mapping = {"quantity": "units", "unit_price": "price"}
        self.raw = b"price,units,comment\n2.25,3,ignore this\n1.10,2,extra\n"

    def orders(self, raw=None):
        return process(self.raw if raw is None else raw, "orders", self.mapping, self.db)

    def test_mapping_load_and_replay(self):
        self.assertEqual(self.orders().total_cents, 895)
        self.assertTrue(self.orders().already_loaded)
        self.assertEqual(stored_count(self.db), 2)
        self.assertEqual(self.orders(b"price,units\n2.25,1\n2.25,N/A\n").code, "invalid_number")
        self.assertEqual(stored_count(self.db), 2)

    def test_full_report_and_atomic_load(self):
        self.orders()
        raw = b'price,units,note\nwrong,three,"two\nlines"\n2,4,ok\n1.234,5,x\n2\n9,0,x\n'
        report = ScanReport()
        run = process(raw, "orders", self.mapping, self.db, report=report)
        self.assertTrue(report.complete)
        self.assertEqual(report.unchecked_columns, ["note"])
        self.assertEqual((report.rows_scanned, run.rows_validated), (5, 1))
        self.assertEqual([(f.line, f.column, f.entered) for f in report.findings], [
            (2, "units", "three"), (2, "price", "wrong"), (5, "price", "1.234"),
            (6, None, "1"), (6, "units", None), (7, "units", "0"),
        ])
        self.assertIn("whole number", report.findings[0].expected)
        self.assertEqual(stored_count(self.db), 2)
        self.assertNotIn("three", run.model_dump_json())

    def test_incomplete_scan_preserves_earlier_errors(self):
        report = ScanReport()
        run = process(b'units,price\nthree,1\n"bad', "orders", self.mapping, self.db, report=report)
        self.assertEqual((run.code, run.row), ("invalid_csv", 3))
        self.assertFalse(report.complete)
        self.assertEqual(report.findings[0].line, 2)
        self.assertFalse(self.db.exists())

    def test_rollback_mid_batch(self):
        self.orders()
        with closing(sqlite3.connect(self.db)) as con:
            con.execute("CREATE TRIGGER reject BEFORE INSERT ON orders WHEN NEW.quantity=7 "
                        "BEGIN SELECT RAISE(ABORT,'fixture'); END")
        self.assertEqual(self.orders(b"units,price\n3,1\n7,1").code, "database_failure")
        self.assertEqual(stored_count(self.db), 2)
        with closing(sqlite3.connect(self.db)) as con:
            self.assertEqual(con.execute("SELECT count(*) FROM imports").fetchone()[0], 1)

    def test_duplicate_inventory_and_dates(self):
        mapping = {"sku": "id", "stock": "available", "as_of": "date"}
        for row, code in [(b"B,0,2026-11-02", "ok"), (b"A,0,", "duplicate"), (b"B,0,2026-02-30", "invalid_date")]:
            run = process(b"id,available,date\nA,1,\n" + row, "inventory", mapping, self.db)
            self.assertEqual(run.code, code)
        self.assertFalse(self.db.exists())

    def test_budget_and_injection_boundary(self):
        docs = corpus()
        big = Document(page_content="x" * 10000, metadata={"id": "oversize"})
        prompt, used = context("What next?", {"stage": "validation"}, [], [big, docs[0]], window=2200)
        self.assertIn("validation", prompt)
        self.assertEqual(used, [docs[0]])
        with self.assertRaises(ValueError):
            context("x" * 12000, {}, [], [])

    def test_real_chroma_with_offline_vectors(self):
        class Embeddings:
            def embed_query(self, text):
                return [1., 0.] if "quantity" in text.lower() else [0., 1.]
            def embed_documents(self, texts):
                return [self.embed_query(t) for t in texts]
        # Ephemeral test storage avoids open SQLite files on Windows.
        import chromadb
        from unittest.mock import patch
        client = chromadb.EphemeralClient()
        with patch("chromadb.PersistentClient", return_value=client):
            index = Index(self.temp.name, "offline-test", Embeddings())
            self.assertEqual(index.collection.count(), len(corpus()))
            self.assertEqual(Index(self.temp.name, "offline-test", Embeddings()).collection.count(), len(corpus()))
            docs = index.search("quantity", "validation")
            self.assertEqual(len(docs), 3)
            self.assertIn("invalid_number", [d.metadata["code"] for d in docs])

    def test_graph_reads_sql_and_rejects_false_citation(self):
        self.orders()
        run = self.orders(b"units,price\nINJECT_ENCODED,9")
        index, model = Mock(), Mock()
        doc = next(d for d in corpus() if d.metadata["code"] == run.code and d.metadata["section"] == "Next check")
        index.search.return_value = [doc]
        chooser, writer = Mock(), Mock()
        chooser.invoke.side_effect = [Choice(action="stored_count"), Choice(action="finish")]
        writer.invoke.return_value = Citation(explanation="The quantity failed validation.", source=doc.metadata["id"], quote=doc.page_content)
        model.with_structured_output.side_effect = lambda schema: chooser if schema is Choice else writer
        result = investigate(run, "How many orders are stored?", index, model, self.db, [], True)
        self.assertEqual(result["tool_trace"], [{"tool":"stored_count","result":2}])
        self.assertEqual(result["model_calls"], 3)
        self.assertEqual(result["citation"], doc.metadata["id"])
        self.assertNotIn("INJECT_ENCODED", str(model.mock_calls) + str(writer.mock_calls))
        writer.invoke.return_value = Citation(explanation="Unsupported", source="invented", quote="no")
        self.assertIsNone(investigate(run, "Next?", index, model, self.db, [])["model_explanation"])
