"""Client issue letter and resubmission comparison. Offline; no AI calls."""
import io
import json
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from claims_onboarding.handoff import FIX, client_letter, compare_submissions, comparison_markdown
from claims_onboarding.readiness import readiness
from claims_onboarding.rules import load_rules, validate

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "claims"
TODAY = date(2026, 11, 5)
KEY = json.loads((EXAMPLE / "answer_key.json").read_text())


def check(raw, specs=None):
    specs = specs or load_rules()
    report = validate(raw, KEY["mapping"], specs, today=TODAY)
    return readiness(specs, KEY["mapping"], report, []), report, specs


def fixed_copy(raw, fields):
    """The sample file with the planted errors in the given fields replaced by valid values from line 2."""
    lines = raw.decode().splitlines()
    header = lines[0].split(",")
    good = lines[1].split(",")
    bad = {p["line"] for p in KEY["planted_errors"] if p["field"] in fields}
    cols = [header.index(KEY["mapping"][f]) for f in fields]
    out = []
    for n, line in enumerate(lines, start=1):
        cells = line.split(",")
        if n in bad and len(cells) == len(header):
            for c in cols:
                cells[c] = good[c]
        out.append(",".join(cells))
    return ("\n".join(out) + "\n").encode()


class LetterTests(unittest.TestCase):
    def setUp(self):
        self.raw = (EXAMPLE / "client_claims.csv").read_bytes()
        self.facts, self.report, self.specs = check(self.raw)

    def test_letter_says_not_ready_and_counts_match_the_report(self):
        letter = client_letter(self.facts, self.report, self.specs, "Acme Health")
        self.assertIn("# Claims file review for Acme Health", letter)
        self.assertIn("**The file is not ready yet.**", letter)
        self.assertIn(f"We found {self.facts['blockers']:,} problems", letter)
        self.assertIn("## Must fix before go-live", letter)
        self.assertIn("## Please review", letter)            # the sample has warnings too

    def test_every_rule_group_appears_with_its_count_and_a_fix(self):
        letter = client_letter(self.facts, self.report, self.specs)
        for r in self.facts["findings_by_rule"]:
            self.assertIn(f"({r['count']:,} rows)", letter)
        self.assertIn("not greater than Total Charges", letter)      # client column names, not platform fields
        self.assertNotIn("billed_amount", letter)
        self.assertNotIn("do not guess", letter)                    # analyst-only notes are left out
        self.assertNotIn("Please check these values.", letter)    # every rule in the sample has specific advice

    def test_examples_are_capped_and_use_client_column_names(self):
        letter = client_letter(self.facts, self.report, self.specs)
        self.assertLessEqual(max(letter.count("| " + str(x["line"]) + " |") for x in self.report.findings), 5)
        self.assertIn(f"### {KEY['mapping']['provider_npi']}:", letter)

    def test_clean_file_letter_says_ready(self):
        specs = load_rules()
        facts = {"decision": "Ready", "rows_checked": 10, "scan_complete": True, "blockers": 0, "warnings": 0,
                 "rows_with_blockers": 0, "findings_by_rule": [], "reasons": []}

        class Empty:
            findings = []
        letter = client_letter(facts, Empty(), specs)
        self.assertIn("ready for go-live", letter)
        self.assertNotIn("## Must fix", letter)

    def test_advice_exists_for_every_rule_kind(self):
        kinds = {r.name for s in load_rules().values() for r in s.rules}
        self.assertFalse(kinds - set(FIX))


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.raw = (EXAMPLE / "client_claims.csv").read_bytes()
        self.before, _, _ = check(self.raw)

    def test_fixing_one_field_shows_as_fixed_and_lowers_blockers(self):
        after, _, _ = check(fixed_copy(self.raw, ["provider_npi"]))
        c = compare_submissions(self.before, after)
        npi = [r for r in c["rows"] if r["field"] == "provider_npi"]
        self.assertTrue(npi and all(r["status"] == "fixed" and r["after"] == 0 for r in npi))
        self.assertLess(c["current_blockers"], c["previous_blockers"])
        self.assertFalse(c["same_file"])
        self.assertEqual(c["new"], 0)

    def test_same_file_is_flagged(self):
        c = compare_submissions(self.before, self.before)
        self.assertTrue(c["same_file"])
        self.assertTrue(all(r["status"] == "unchanged" for r in c["rows"]))
        self.assertIn("not a resubmission", comparison_markdown(c))

    def test_new_and_worse_groups(self):
        prev = {"decision": "Ready", "findings_by_rule": [{"field": "a", "rule": "x", "severity": "warning", "count": 1}]}
        cur = {"decision": "Not ready", "findings_by_rule": [{"field": "a", "rule": "x", "severity": "warning", "count": 3},
                                                             {"field": "b", "rule": "y", "severity": "blocker", "count": 2}]}
        c = compare_submissions(prev, cur)
        self.assertEqual([(r["field"], r["status"]) for r in c["rows"]], [("b", "new"), ("a", "worse")])
        self.assertIn("Ready → **Not ready**", comparison_markdown(c))


class HandoffPageTests(unittest.TestCase):
    PAGE = str(ROOT / "pages/3_Claims_Onboarding.py")

    def test_letter_and_comparison_on_the_page(self):
        raw = (EXAMPLE / "client_claims.csv").read_bytes()
        previous, _, _ = check(raw)
        previous_json = json.dumps({**previous, "source_sha256": "earlier-file"}).encode()

        def uploader(label, *a, key=None, **kw):
            data = previous_json if key == "claims_previous_report" else raw
            f = io.BytesIO(data)
            f.size = len(data)
            return f

        with patch("streamlit.file_uploader", side_effect=uploader):
            app = AppTest.from_file(self.PAGE, default_timeout=60).run()
            for sb in app.selectbox:
                field = sb.label.split(" ")[0]
                if field in KEY["mapping"]:
                    sb.select(KEY["mapping"][field])
            app.run()
            next(b for b in app.button if b.label.startswith("Approve")).click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.text_input[0].value, "the client")
            labels = [m.label for m in app.metric]
            self.assertIn("Rule groups fixed", labels)
            self.assertEqual([e.value for e in app.error], ["Decision: Not ready"])   # no bad-report error


if __name__ == "__main__":
    unittest.main()
