"""Unit checks for mapping confidence, exception tracking, readiness, recovery, downstream idempotency and AI guards."""
import io
import json
import unittest
from types import SimpleNamespace

from sqlalchemy import select

from claims_onboarding import synth
from claims_onboarding.mapping import Suggestion
from claims_onboarding.rules import load_rules
from claims_platform import comms, downstream, processing
from claims_platform.demo import VENDOR_C, build_file
from claims_platform.mapping_service import check_mapping, suggest
from claims_platform.models import DownstreamBatch, DownstreamRecord, ExceptionItem, Export
from claims_platform.scenarios import Api, approve_mapping, new_client, prepare_mapping, setup_team, upload, validate
from orders_assistant.explain import ExplanationError

from _platform_env import PASSWORD, Platform

SPECS = load_rules()


class MappingConfidenceTests(unittest.TestCase):
    def test_sample_layout_flags_the_two_npi_columns_as_ambiguous(self):
        s = suggest(synth.CLIENT_COLUMNS, SPECS)["suggestions"]
        self.assertEqual(s["provider_npi"]["column"], "Rendering NPI")
        self.assertEqual(s["provider_npi"]["level"], "ambiguous")
        self.assertIn("Billing Prov NPI", s["provider_npi"]["alternatives"])
        self.assertEqual(s["claim_id"]["level"], "high")
        self.assertFalse(s["claim_id"]["needs_confirmation"])

    def test_platform_abstains_instead_of_guessing(self):
        s = suggest(synth.CLIENT_COLUMNS, SPECS)["suggestions"]
        for f in ("diagnosis_code", "procedure_code", "billed_amount"):
            self.assertIsNone(s[f]["column"])
            self.assertEqual(s[f]["level"], "none")
            self.assertTrue(s[f]["needs_confirmation"])

    def test_ai_agreement_raises_confidence_and_disagreement_is_flagged(self):
        def fake_ai(headers, specs):
            out = {f: Suggestion(f, None, "none", "") for f in specs}
            out["claim_id"] = Suggestion("claim_id", "Clm_Nbr", "gemini", "Claim number.")
            out["diagnosis_code"] = Suggestion("diagnosis_code", "Primary Dx", "gemini", "Dx is diagnosis.")
            out["member_id"] = Suggestion("member_id", "Group Nbr", "gemini", "Wrong on purpose.")
            return out
        r = suggest(synth.CLIENT_COLUMNS, SPECS, use_ai=True, ai_suggest=fake_ai)
        s = r["suggestions"]
        self.assertTrue(r["ai_used"])
        self.assertEqual(s["claim_id"]["level"], "high")
        self.assertEqual((s["diagnosis_code"]["column"], s["diagnosis_code"]["level"]), ("Primary Dx", "medium"))
        self.assertTrue(s["diagnosis_code"]["needs_confirmation"])
        self.assertEqual(s["member_id"]["level"], "ambiguous")
        self.assertIn("Subscriber Ref", s["member_id"]["alternatives"])

    def test_ai_failure_keeps_name_matching(self):
        def broken(headers, specs):
            raise ExplanationError("Gemini was unavailable.")
        r = suggest(synth.CLIENT_COLUMNS, SPECS, use_ai=True, ai_suggest=broken)
        self.assertFalse(r["ai_used"])
        self.assertEqual(r["ai_error"], "Gemini was unavailable.")
        self.assertEqual(r["suggestions"]["claim_id"]["column"], "Clm_Nbr")

    def test_check_mapping_rejects_duplicates_unknown_columns_and_unconfirmed_fields(self):
        sugg = suggest(synth.CLIENT_COLUMNS, SPECS)["suggestions"]
        chosen = dict(synth.ANSWER_KEY, member_id="Clm_Nbr")
        problems, _, _ = check_mapping(synth.CLIENT_COLUMNS, SPECS, sugg, chosen, list(SPECS))
        self.assertTrue(any("more than one field" in p for p in problems))
        problems, _, _ = check_mapping(synth.CLIENT_COLUMNS, SPECS, sugg, dict(synth.ANSWER_KEY, claim_id="Nope"),
                                       list(SPECS))
        self.assertTrue(any("not in the file" in p for p in problems))
        problems, corrections, unconfirmed = check_mapping(synth.CLIENT_COLUMNS, SPECS, sugg, synth.ANSWER_KEY, [])
        self.assertEqual(unconfirmed, ["provider_npi"])     # changed fields count as explicit decisions
        self.assertEqual({c["field"] for c in corrections}, {"diagnosis_code", "procedure_code", "billed_amount"})


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.p = Platform(export_batch_size=100)
        self.p.__enter__()
        self.api = Api(self.p.client)
        self.api.login("admin", PASSWORD)
        setup_team(self.api, PASSWORD)
        self.c = new_client(self.api, "ana", "U-UNIT", "Unit (synthetic)", ["priya"])

    def tearDown(self):
        self.p.__exit__(None, None, None)

    def onboard(self, raw):
        sub = upload(self.api, "ana", self.c["id"], "u.csv", raw)["submission"]
        approve_mapping(self.api, "priya", prepare_mapping(self.api, "ana", sub["id"], synth.ANSWER_KEY)["id"])
        return sub, validate(self.api, "ana", sub["id"])

    def test_validation_needs_an_approved_mapping(self):
        raw, _ = build_file(rows=50, seed=2)
        sub = upload(self.api, "ana", self.c["id"], "u.csv", raw)["submission"]
        r = self.api.post("ana", f"/api/submissions/{sub['id']}/runs")
        self.assertEqual(r.status_code, 409)
        prepare_mapping(self.api, "ana", sub["id"], synth.ANSWER_KEY)   # submitted but not yet approved
        self.assertEqual(self.api.post("ana", f"/api/submissions/{sub['id']}/runs").status_code, 409)

    def test_never_ready_while_an_open_blocker_exception_remains(self):
        raw, _ = build_file(rows=300, seed=3)
        sub, run = self.onboard(raw)
        self.assertEqual(run["decision"], "Ready")
        with self.p.Session() as db:   # a blocker group left open (for example from a scan that stopped early)
            db.add(ExceptionItem(client_id=self.c["id"], field="(file)", rule="file must be read completely",
                                 severity="blocker", status="open", first_count=1, current_count=1,
                                 first_run_id=run["id"], last_run_id=run["id"], first_submission=1, last_submission=1))
            db.commit()
        state = self.api.ok("GET", "ana", f"/api/clients/{self.c['id']}/readiness")
        self.assertFalse(state["ready_for_approval"])
        self.assertEqual(self.api.post("priya", f"/api/clients/{self.c['id']}/golive",
                                       json={"approve": True, "comment": "x"}).status_code, 409)

    def test_incomplete_scan_does_not_resolve_anything(self):
        from claims_platform.demo import corrupted
        raw, _ = build_file(rows=300, seed=4, breaks=[("provider_npi", "exactly 10 digits", 2)])
        self.onboard(raw)
        # The next file cannot be read to the end. Its NPI errors are gone, but that proves nothing,
        # so the NPI exception must stay open.
        sub2 = upload(self.api, "ana", self.c["id"], "u2.csv", corrupted(build_file(rows=300, seed=4)[0]))["submission"]
        run2 = validate(self.api, "ana", sub2["id"])
        self.assertFalse(run2["scan_complete"])
        with self.p.Session() as db:
            npi = db.execute(select(ExceptionItem).where(ExceptionItem.field == "provider_npi")).scalar_one()
            self.assertEqual(npi.status, "open")

    def test_warning_must_be_dispositioned_before_go_live(self):
        raw, _ = build_file(rows=300, seed=8, breaks=[("place_of_service", "exactly 2 digits", 2)])
        sub, run = self.onboard(raw)
        self.assertEqual(run["decision"], "Ready")   # warnings do not block the file-level decision
        state = self.api.ok("GET", "ana", f"/api/clients/{self.c['id']}/readiness")
        self.assertFalse(state["ready_for_approval"])
        exc = self.api.ok("GET", "ana", f"/api/clients/{self.c['id']}/exceptions")[0]
        short = self.api.patch("priya", f"/api/exceptions/{exc['id']}", json={"status": "accepted", "note": "ok"})
        self.assertEqual(short.status_code, 422)
        analyst = self.api.patch("ana", f"/api/exceptions/{exc['id']}",
                                 json={"status": "accepted", "note": "Client confirmed these codes."})
        self.assertEqual(analyst.status_code, 403)
        self.api.ok("PATCH", "priya", f"/api/exceptions/{exc['id']}",
                    json={"status": "accepted", "note": "Client confirmed these legacy codes."})
        self.assertTrue(self.api.ok("GET", "ana", f"/api/clients/{self.c['id']}/readiness")["ready_for_approval"])

    def test_go_live_needs_an_independent_approver(self):
        raw, _ = build_file(rows=120, seed=9)
        sub = upload(self.api, "admin", self.c["id"], "u.csv", raw)["submission"]
        m = self.api.ok("POST", "admin", f"/api/submissions/{sub['id']}/mappings", json={"use_ai": False})
        chosen = {f: x["column"] for f, x in m["suggestions"].items()} | synth.ANSWER_KEY
        self.api.ok("PUT", "admin", f"/api/mappings/{m['id']}", json={
            "mapping": chosen, "submit": True,
            "confirmed_fields": [f for f, x in m["suggestions"].items() if x["needs_confirmation"]]})
        approve_mapping(self.api, "priya", m["id"])
        validate(self.api, "admin", sub["id"])
        own = self.api.post("admin", f"/api/clients/{self.c['id']}/golive", json={"approve": True, "comment": "mine"})
        self.assertEqual(own.status_code, 403)
        self.api.ok("POST", "priya", f"/api/clients/{self.c['id']}/golive", json={"approve": True, "comment": "ok"})

    def test_recovery_marks_in_flight_exports_failed_and_resume_completes(self):
        raw, _ = build_file(rows=450, seed=10)
        self.onboard(raw)
        self.api.ok("POST", "priya", f"/api/clients/{self.c['id']}/golive", json={"approve": True, "comment": "ok"})
        self.api.ok("PUT", "admin", "/api/admin/simulation",
                    json={"downstream_fault": {"mode": "outage", "from_batch": 2, "remaining": 3}})
        self.api.ok("POST", "ana", f"/api/clients/{self.c['id']}/exports")
        with self.p.Session() as db:   # pretend the process died while the export was running
            exp = db.execute(select(Export)).scalar_one()
            exp.status = "in_progress"
            db.commit()
            result = processing.recover_interrupted(db)
            db.commit()
            self.assertEqual(result["exports"], 1)
            self.assertEqual(exp.status, "failed")
            self.assertIn("Retry resumes from batch 3", exp.last_error)
        self.api.ok("PUT", "admin", "/api/admin/simulation", json={})
        self.api.ok("POST", "ana", f"/api/exports/{exp.id}/retry")
        with self.p.Session() as db:
            exp = db.get(Export, exp.id)
            self.assertEqual((exp.status, exp.sent_records, exp.attempts), ("completed", 450, 2))
            self.assertEqual(db.execute(select(DownstreamRecord)).scalars().all().__len__(), 450)

    def test_downstream_dedupes_claims_across_exports(self):
        raw, _ = build_file(rows=200, seed=12)
        self.onboard(raw)
        self.api.ok("POST", "priya", f"/api/clients/{self.c['id']}/golive", json={"approve": True, "comment": "ok"})
        self.api.ok("POST", "ana", f"/api/clients/{self.c['id']}/exports")
        with self.p.Session() as db:
            export_id = db.execute(select(Export.id)).scalar_one()
        recs = [{"claim_id": "CLM1000000"}, {"claim_id": "NEW-1"}, {"claim_id": "NEW-1"}]
        ack = downstream.receive_batch(self.p.Session, self.p.app.state.cipher, self.c["id"], export_id, "k" * 64, recs)
        self.assertEqual((ack["accepted"], ack["duplicates"], ack["replayed"]), (1, 2, False))
        again = downstream.receive_batch(self.p.Session, self.p.app.state.cipher, self.c["id"], export_id, "k" * 64, recs)
        self.assertTrue(again["replayed"])
        with self.p.Session() as db:
            self.assertEqual(len(db.execute(select(DownstreamRecord)).scalars().all()), 201)
            self.assertEqual(len(db.execute(select(DownstreamBatch)).scalars().all()), 3)

    def test_mapping_layout_change_requires_a_new_mapping(self):
        raw, _ = build_file(rows=60, seed=13)
        self.onboard(raw)
        other, _ = build_file(rows=60, seed=14, rename=VENDOR_C)
        sub2 = upload(self.api, "ana", self.c["id"], "v.csv", other)["submission"]
        r = self.api.post("ana", f"/api/submissions/{sub2['id']}/runs")
        self.assertEqual(r.status_code, 409)
        self.assertIn("not in this file", r.json()["detail"])

    def test_rule_draft_with_unknown_phrase_is_rejected_with_line_number(self):
        r = self.api.post("ana", f"/api/clients/{self.c['id']}/rulesets",
                          json={"text": "claim_id | id | required, sparkly", "note": ""})
        self.assertEqual(r.status_code, 422)
        self.assertIn("Line 1", r.json()["detail"])

    def test_milestones_follow_the_workflow(self):
        raw, _ = build_file(rows=80, seed=15)
        self.onboard(raw)
        ms = {m["key"]: m["status"] for m in self.api.ok("GET", "ana", f"/api/clients/{self.c['id']}/milestones")}
        self.assertEqual(ms["kickoff"], "done")
        self.assertEqual(ms["mapping_approved"], "done")
        self.assertEqual(ms["first_validation"], "done")
        self.assertEqual(ms["go_live_approved"], "not_started")


class AiGuardTests(unittest.TestCase):
    def exc(self):
        return SimpleNamespace(field="provider_npi", client_column="Rendering NPI", rule="exactly 10 digits",
                               severity="blocker", current_count=6)

    def fake_gemini(self, text, sent):
        class Resp(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                self.close()

        def opener(request, timeout=None):
            sent.append(json.loads(request.data))
            payload = {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": text}]}}]}
            return Resp(json.dumps(payload).encode())
        return opener

    def test_explanation_is_deterministic_and_complete(self):
        out = comms.explanation(self.exc(), SPECS)
        self.assertIn("6 rows", out["summary"])
        self.assertIn("blocker", out["summary"])
        self.assertTrue(out["how_to_fix"] and out["why_it_matters"])

    def test_ai_explanation_sends_no_cell_values_and_rejects_invented_figures(self):
        import os
        from unittest.mock import patch
        sent = []
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key", "GEMINI_MODEL": "test-model"}):
            base = comms.explanation(self.exc(), SPECS)
            good = comms.ai_explanation(self.exc(), base, opener=self.fake_gemini(
                "Six rows have NPIs that are not exactly 10 digits. Please correct them and resend.", sent))
            self.assertIn("10 digits", good)
            with self.assertRaises(ExplanationError):
                comms.ai_explanation(self.exc(), base, opener=self.fake_gemini(
                    "About 95% of NPIs fail; 600 rows need work before go-live.", sent))
        prompt = json.dumps(sent)
        for value in ("123456789", "CLM", "E11.9", "2025-"):
            self.assertNotIn(value, prompt)


if __name__ == "__main__":
    unittest.main()
