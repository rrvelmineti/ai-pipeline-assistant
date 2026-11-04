import unittest
from unittest.mock import Mock, patch
from orders_assistant.csv_check import ColumnRule as R, check, infer, suggest
from orders_assistant.csv_guidance import ReadChoice, explain_issue
from orders_assistant.investigate import Citation, corpus


class CSVReviewTests(unittest.TestCase):
    def test_headings_override_invalid_sample_and_preserve_ids(self):
        headers, rules = suggest(b"Quantity,UnitPrice,Product name,Postal code,Purchase date\nthree,ten,Book,00123,2026-11-03\n")
        self.assertEqual([rules[h].kind for h in headers], ["Whole number", "Number", "Text", "Identifier", "Date"])
        self.assertEqual(rules["Purchase date"].date_format, "YYYY-MM-DD")

    def test_scan_all_cells_and_suggest_without_changing(self):
        raw = b"quantity,amount,name\nthree,ten,123\n2.5,NaN,456\n,,\n"
        _, rules = suggest(raw)
        report = check(raw, rules)
        self.assertEqual(report.issue_count, 9)
        self.assertEqual(report.rows_checked, 3)
        self.assertEqual(report.findings[0]["entered"], "three")
        self.assertIn("Possible replacement: 3.", report.findings[0]["suggestion"])
        self.assertEqual(report.status, "issues_found")
        self.assertEqual(raw.splitlines()[1], b"three,ten,123")

    def test_no_business_numeric_ranges_or_totals(self):
        report = check(b"quantity,price\n0,-2.123456\n99999999999999999999999999,1000000000000\n",
                       {"quantity": R("Whole number"), "price": R("Number")})
        self.assertEqual(report.status, "no_format_issues")
        self.assertNotIn("total", str(report.to_dict()))

    def test_whole_and_integer(self):
        for val, whole, integer in [("3", True, True), ("3.0", False, False),
                                    ("-3", False, True), ("+3", False, True), ("three", False, False)]:
            for kind, valid in [("Whole number", whole), ("Integer", integer)]:
                self.assertEqual(check(("x\n"+val).encode(), {"x": R(kind)}).issue_count == 0, valid)

    def test_text_ids_and_blank_policy(self):
        report = check("name,id,note\n李雷,0012,\n123,A12,\n".encode(),
                       {"name": R("Text"), "id": R("Identifier"), "note": R("Text", allow_blank=True)})
        self.assertEqual(report.issue_count, 1)
        self.assertEqual(report.findings[0]["column"], "name")

    def test_date_consistency_calendar_and_ambiguity(self):
        self.assertIsNone(infer("date", ["03/04/2026"]).date_format)
        rules = {"date": R("Date", "DD/MM/YYYY")}
        report = check(b"date\n31/01/2026\n2026-01-31\n31/02/2026\n", rules)
        self.assertEqual(report.issue_count, 2)
        self.assertIn("different date format", report.findings[0]["suggestion"])
        self.assertEqual(check(b"date\n29/02/2024", rules).issue_count, 0)
        self.assertEqual(check(b"date\n29/02/2025", rules).issue_count, 1)
        self.assertEqual(check(b"date\n03/04/2026", {"date": R("Date")}).status, "incomplete")

    def test_unknown_columns_are_not_clean(self):
        report = check(b"x\n42\n", {"x": R()})
        self.assertEqual(report.status, "partial_coverage")
        self.assertEqual(report.unchecked_columns, ["x"])
        self.assertEqual(infer("unknown", ["", ""]).kind, "Not checked")

    def test_physical_line_numbers_with_embedded_newlines(self):
        raw = b'name,quantity\n"First\nLast",3\nOther,three\n'
        report = check(raw, {"name": R("Text"), "quantity": R("Whole number")})
        self.assertEqual(report.findings[0]["line"], 4)
        self.assertEqual(report.rows_checked, 2)

    def test_wrong_field_count_continues(self):
        report = check(b"x,y\n1\n2,bad\n3,4\n", {"x": R("Number"), "y": R("Number")})
        self.assertEqual(report.rows_checked, 3)
        self.assertEqual(report.issue_count, 2)

    def test_empty_bad_header_encoding_and_quotes(self):
        for raw in (b"", b"x", b"x,x\n1,2", b" x ,X\n1,2", b",y\n1,2", b"x\n\xff", b'x\n"oops'):
            self.assertFalse(check(raw, {"x": R("Text")}).complete)

    def test_report_caps_continue_counting_and_partial_scan(self):
        with patch("orders_assistant.csv_check.MAX_FINDINGS", 1):
            report = check(b"x\nwrong\nwrong\nwrong", {"x": R("Number")})
        self.assertEqual(report.issue_count, 3)
        self.assertEqual(len(report.findings), 1)
        self.assertTrue(report.to_dict()["findings_truncated"])
        with patch("orders_assistant.csv_check.MAX_RECORDS", 1):
            report = check(b"x\n1\n2", {"x": R("Number")})
        self.assertFalse(report.complete)
        self.assertEqual(report.rows_checked, 1)

    def test_scans_errors_beyond_inference_sample(self):
        raw = b"quantity\n" + b"3\n" * 501 + b"three\n"
        _, rules = suggest(raw)
        report = check(raw, rules)
        self.assertEqual(report.rows_checked, 502)
        self.assertEqual(report.findings[0]["line"], 503)

    def test_rag_citation_and_redaction(self):
        issue = {"code": "invalid_type", "line": 3, "column": "PRIVATE_HEADER", "entered": "PRIVATE_CELL"}
        doc = next(d for d in corpus() if d.metadata["code"] == "csv_type" and d.metadata["section"] == "Next check")
        index, llm = Mock(), Mock()
        index.search.return_value = [doc]
        llm.with_structured_output.return_value.invoke.return_value = Citation(explanation="Type mismatch.", source=doc.metadata["id"], quote=doc.page_content)
        result = explain_issue(issue, index, llm)
        self.assertEqual(result["citation"], doc.metadata["id"])
        self.assertNotIn("PRIVATE", str(index.mock_calls) + str(llm.mock_calls))
        llm.with_structured_output.return_value.invoke.return_value = Citation(explanation="Guess", source="fake", quote="fake")
        self.assertIsNone(explain_issue(issue, index, llm)["model_explanation"])

    def test_agent_bounded_reads(self):
        issue = {"code": "missing_value", "line": 9}
        index, llm, chooser, writer = Mock(), Mock(), Mock(), Mock()
        index.search.return_value = []
        chooser.invoke.side_effect = [ReadChoice(action="evidence"), ReadChoice(action="search")]
        writer.invoke.return_value = Citation(explanation="Unknown", source=None, quote=None)
        llm.with_structured_output.side_effect = lambda schema: chooser if schema is ReadChoice else writer
        result = explain_issue(issue, index, llm, agent=True)
        self.assertEqual(result["model_calls"], 3)
        self.assertEqual([x["tool"] for x in result["tool_trace"]], ["evidence", "search"])
        self.assertIsNone(result["next_check"])
