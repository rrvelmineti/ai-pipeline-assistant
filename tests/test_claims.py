"""Offline tests for claims onboarding. No test calls a live AI service."""
import io
import json
import os
import unittest
from collections import Counter
from datetime import date
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from claims_onboarding.mapping import (check_model_mapping, correction_log, gemini_suggest,
                                       heuristic_suggest)
from claims_onboarding.readiness import check_summary, gemini_summary, readiness, written_summary
from claims_onboarding.rules import RulesError, load_rules, parse_rules, validate
from claims_onboarding.synth import ANSWER_KEY, CLIENT_COLUMNS, generate
from orders_assistant.explain import ExplanationError

ROOT = Path(__file__).resolve().parents[1]
TODAY = date(2026, 11, 5)
GEMINI = {"GEMINI_API_KEY": "test-key", "GEMINI_MODEL": "test-model"}


def fake_gemini(text, finish="STOP"):
    """An opener that returns a canned Gemini response and records what was sent."""
    sent = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, n):
            return json.dumps({"candidates": [{"finishReason": finish,
                                               "content": {"parts": [{"text": text}]}}]}).encode()

    def opener(request, timeout):
        sent.append(json.loads(request.data))
        return Response()
    opener.sent = sent
    return opener


def csv_bytes(rows, header="claim_id,paid,billed,dos,dob"):
    return (header + "\n" + "\n".join(rows) + "\n").encode()


SMALL_RULES = """
claim_id | Claim number | required, unique
billed   | Billed       | required, number, not negative
paid     | Paid         | required, number, not greater than billed
dob      | Birth date   | date YYYY-MM-DD
dos      | Service date | required, date YYYY-MM-DD, not in the future, not before dob (warning)
"""
SMALL_MAP = {"claim_id": "claim_id", "billed": "billed", "paid": "paid", "dos": "dos", "dob": "dob"}


class RulesFileTests(unittest.TestCase):
    def test_shipped_rules_file_parses(self):
        specs = load_rules()
        self.assertEqual(set(specs), set(ANSWER_KEY))
        self.assertTrue(specs["claim_id"].required)
        self.assertFalse(specs["place_of_service"].required)
        self.assertEqual(specs["place_of_service"].rules[0].severity, "warning")

    def test_unknown_phrase_names_the_line(self):
        with self.assertRaises(RulesError) as err:
            parse_rules("a | A | required\nb | B | must be lovely")
        self.assertIn("Line 2", str(err.exception))
        self.assertIn("must be lovely", str(err.exception))

    def test_cross_field_rule_needs_known_typed_field(self):
        for text in ("a | A | number, not greater than b",
                     "a | A | number, not greater than b\nb | B | required",
                     "a | A | date YYYY-MM-DD, not before b\nb | B | number"):
            with self.subTest(text=text), self.assertRaises(RulesError):
                parse_rules(text)

    def test_bad_date_format_and_conflicting_types_rejected(self):
        with self.assertRaises(RulesError):
            parse_rules("a | A | date DD.MM.YY")
        with self.assertRaises(RulesError):
            parse_rules("a | A | number, date YYYY-MM-DD")


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.specs = parse_rules(SMALL_RULES)

    def test_each_rule_reports_line_and_severity(self):
        raw = csv_bytes(["C1,10,20,2026-01-01,1990-01-01",      # clean
                         "C1,30,20,2026-01-01,1990-01-01",      # duplicate + paid > billed
                         "C3,5,$20,2027-01-01,1990-01-01",      # billed not a number; future date
                         "C4,5,20,2026-01-01,2026-06-01",       # service before dob (warning)
                         ",-5,-1,01/02/2026,"])                 # missing id, negative billed, bad date
        report = validate(raw, SMALL_MAP, self.specs, today=TODAY)
        got = Counter((f["line"], f["field"], f["rule"], f["severity"]) for f in report.findings)
        self.assertEqual(got, Counter({
            (3, "claim_id", "unique", "blocker"): 1, (3, "paid", "not greater than billed", "blocker"): 1,
            (4, "billed", "number", "blocker"): 1, (4, "dos", "not in the future", "blocker"): 1,
            (5, "dos", "not before dob", "warning"): 1, (6, "claim_id", "required", "blocker"): 1,
            (6, "billed", "not negative", "blocker"): 1, (6, "dos", "date YYYY-MM-DD", "blocker"): 1}))
        self.assertEqual((report.blockers, report.warnings, report.rows_checked), (7, 1, 5))
        self.assertTrue(report.complete)

    def test_unmapped_required_or_reused_column_stops_before_scanning(self):
        raw = csv_bytes(["C1,10,20,2026-01-01,1990-01-01"])
        for mapping in ({**SMALL_MAP, "paid": None}, {**SMALL_MAP, "paid": "billed"}, {**SMALL_MAP, "paid": "nope"}):
            with self.subTest(mapping=mapping):
                report = validate(raw, mapping, self.specs, today=TODAY)
                self.assertFalse(report.complete)
                self.assertEqual(report.rows_checked, 0)

    def test_wrong_field_count_is_reported_and_scan_continues(self):
        raw = csv_bytes(["C1,10,20", "C2,10,20,2026-01-01,1990-01-01"])
        report = validate(raw, SMALL_MAP, self.specs, today=TODAY)
        self.assertEqual(report.rows_checked, 2)
        self.assertEqual(report.findings[0]["field"], "(row)")

    def test_synthetic_file_finds_exactly_the_planted_errors(self):
        raw, key = generate()
        report = validate(raw, key["mapping"], load_rules(), today=TODAY)
        got = Counter((f["line"], f["field"], f["rule"]) for f in report.findings)
        want = Counter((p["line"], p["field"], p["rule"]) for p in key["planted_errors"])
        self.assertEqual(got, want)
        self.assertEqual(report.rows_checked, 2000)

    def test_generator_is_deterministic_and_matches_committed_example(self):
        raw, key = generate()
        self.assertEqual(raw, generate()[0])
        self.assertEqual(raw, (ROOT / "examples/claims/client_claims.csv").read_bytes())
        self.assertEqual(key, json.loads((ROOT / "examples/claims/answer_key.json").read_text()))


class MappingTests(unittest.TestCase):
    def setUp(self):
        self.specs = load_rules()

    def test_name_matching_never_reuses_a_column_and_leaves_unclear_fields_blank(self):
        suggestions = heuristic_suggest(CLIENT_COLUMNS, self.specs)
        used = [s.column for s in suggestions.values() if s.column]
        self.assertEqual(len(used), len(set(used)))
        for f, s in suggestions.items():
            self.assertIn(s.column, (None, ANSWER_KEY[f]), f)   # blank is allowed, a wrong guess is not
        self.assertEqual(suggestions["provider_npi"].column, "Rendering NPI")  # not the billing NPI

    def test_gemini_receives_headings_but_never_cell_values(self):
        answer = {"mappings": [{"field": f, "column": c, "reason": "Matches."} for f, c in ANSWER_KEY.items()]}
        opener = fake_gemini(json.dumps(answer))
        with patch.dict(os.environ, {}, clear=True):
            result = gemini_suggest(CLIENT_COLUMNS, self.specs, secrets=GEMINI, opener=opener)
        self.assertEqual({f: s.column for f, s in result.items()}, ANSWER_KEY)
        self.assertTrue(all(s.source == "gemini" for s in result.values()))
        prompt = opener.sent[0]["contents"][0]["parts"][0]["text"]
        self.assertIn("Rendering NPI", prompt)
        raw, _ = generate()
        values = {v for line in raw.decode().splitlines()[1:200] for v in line.split(",")}
        data_values = {v for v in values if any(ch.isdigit() for ch in v) and len(v) >= 4}
        self.assertGreater(len(data_values), 500)
        self.assertFalse([v for v in data_values if v in prompt])

    def test_invalid_model_mappings_are_rejected(self):
        good = [{"field": f, "column": c} for f, c in ANSWER_KEY.items()]
        bad = {
            "invented heading": [{**good[0], "column": "Claim Number"}, *good[1:]],
            "reused heading": [{**good[0], "column": good[1]["column"]}, *good[1:]],
            "missing field": good[1:],
            "unknown field": [*good, {"field": "secret", "column": None}],
        }
        for name, entries in bad.items():
            with self.subTest(name), self.assertRaises(ValueError):
                check_model_mapping({"mappings": entries}, CLIENT_COLUMNS, self.specs)
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(ExplanationError):
            gemini_suggest(CLIENT_COLUMNS, self.specs, secrets=GEMINI,
                           opener=fake_gemini(json.dumps({"mappings": bad["invented heading"]})))

    def test_correction_log_records_every_change(self):
        suggestions = heuristic_suggest(CLIENT_COLUMNS, self.specs)
        log = correction_log(suggestions, ANSWER_KEY)
        self.assertEqual({c["field"] for c in log}, {f for f, s in suggestions.items() if s.column != ANSWER_KEY[f]})
        self.assertTrue(all(c["chosen_column"] == ANSWER_KEY[c["field"]] for c in log))


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.specs = parse_rules(SMALL_RULES)

    def facts(self, rows, mapping=SMALL_MAP):
        report = validate(csv_bytes(rows), mapping, self.specs, today=TODAY)
        return readiness(self.specs, mapping, report, correction_log({}, mapping))

    def test_ready_only_with_no_blockers_and_a_complete_scan(self):
        ready = self.facts(["C1,10,20,2026-01-01,1990-01-01", "C2,10,20,2026-01-01,2026-06-01"])
        self.assertEqual((ready["decision"], ready["blockers"], ready["warnings"]), ("Ready", 0, 1))
        self.assertEqual(self.facts(["C1,30,20,2026-01-01,1990-01-01"])["decision"], "Not ready")
        unmapped = self.facts(["C1,10,20,2026-01-01,1990-01-01"], {**SMALL_MAP, "paid": None})
        self.assertEqual(unmapped["decision"], "Not ready")
        self.assertIn("paid", unmapped["reasons"][0])

    def test_written_summary_uses_only_report_figures(self):
        facts = self.facts(["C1,30,20,2026-01-01,1990-01-01", "C1,10,$5,2026-01-01,1990-01-01"])
        summary = written_summary(facts)
        self.assertEqual(check_summary(summary, facts), summary)

    def test_ai_summary_with_invented_figure_or_wrong_decision_is_rejected(self):
        facts = self.facts(["C1,30,20,2026-01-01,1990-01-01"])
        with self.assertRaises(ValueError):
            check_summary("Not ready: 1 blocker found, about 95% of the file is clean.", facts)
        with self.assertRaises(ValueError):
            check_summary("The file is ready for go-live with 1 blocker to watch.", facts)
        ok = "The file is not ready. 1 row was checked and it has 1 blocker in paid."
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(gemini_summary(facts, secrets=GEMINI, opener=fake_gemini(ok)), ok)
            with self.assertRaises(ExplanationError):
                gemini_summary(facts, secrets=GEMINI, opener=fake_gemini("Not ready: 3 blockers in 7 rows."))

    def test_ai_summary_prompt_excludes_cell_values(self):
        facts = self.facts(["CLM-SECRET-9,30,20,2026-01-01,1990-01-01"])
        opener = fake_gemini("The file is not ready. 1 row was checked and it has 1 blocker.")
        with patch.dict(os.environ, {}, clear=True):
            gemini_summary(facts, secrets=GEMINI, opener=opener)
        self.assertNotIn("CLM-SECRET-9", json.dumps(opener.sent))


def uploaded(raw):
    upload = io.BytesIO(raw)
    upload.size = len(raw)
    return upload


class ClaimsPageTests(unittest.TestCase):
    PAGE = str(ROOT / "pages/3_Claims_Onboarding.py")

    def test_upload_required(self):
        app = AppTest.from_file(self.PAGE).run()
        self.assertFalse(app.exception)
        self.assertFalse(app.selectbox or app.metric)

    def test_full_flow_unmapped_fields_block_until_analyst_maps_them(self):
        raw = (ROOT / "examples/claims/client_claims.csv").read_bytes()
        with patch("streamlit.file_uploader", return_value=uploaded(raw)):
            app = AppTest.from_file(self.PAGE, default_timeout=60).run()
            approve = lambda: next(b for b in app.button if b.label.startswith("Approve"))
            self.assertTrue(approve().disabled)
            for sb in app.selectbox:
                field = sb.label.split(" ")[0]
                if field in ANSWER_KEY:
                    sb.select(ANSWER_KEY[field])
            app.run()
            self.assertFalse(approve().disabled)
            approve().click().run()
            self.assertFalse(app.exception)
            facts = app.session_state["claims_facts"]
            self.assertEqual(facts["decision"], "Not ready")
            self.assertEqual(facts["rows_checked"], 2000)
            self.assertEqual(len(facts["mapping_corrections"]), 3)
            # Changing a mapping clears the stale report.
            next(sb for sb in app.selectbox if sb.label.startswith("billed_amount")).select("Allowed Amt").run()
            self.assertNotIn("claims_facts", app.session_state)

    def test_broken_rules_edit_shows_error_instead_of_checking(self):
        with patch("streamlit.file_uploader", return_value=uploaded(b"a,b\n1,2\n")):
            app = AppTest.from_file(self.PAGE).run()
            app.text_area[0].input("claim_id | Claim | required, sparkly").run()
            self.assertFalse(app.exception)
            self.assertIn("sparkly", app.error[0].value)


if __name__ == "__main__":
    unittest.main()
