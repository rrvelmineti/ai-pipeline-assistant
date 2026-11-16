"""Test scenarios A–F from the pilot plan, driven through the HTTP API exactly as people would use it.

Each scenario records checks: an acceptance criterion, what was expected and what actually happened.
Used by the automated tests, by `python -m evaluation.platform_scenarios`, and to seed the demo.
"""
import contextlib
import hashlib
import io
import json
import os
import time
import zipfile
from collections import Counter

from claims_onboarding import synth
from claims_onboarding.rules import BLOCKER, WARNING

from .config import ROOT
from .demo import VENDOR_C, VENDOR_C_MAPPING, build_file, corrupted, rules_with_us_dates, truncated

EXAMPLE = ROOT / "examples" / "claims"
TEAM = [("ana", "Ana Analyst", "implementation_analyst"), ("sam", "Sam Analyst", "implementation_analyst"),
        ("priya", "Priya Approver", "approver"), ("omar", "Omar Approver", "approver"),
        ("birch.contact", "Birch data contact", "client_contact"), ("fir.contact", "Fir data contact", "client_contact")]
STATUS_RULE = "one of paid / denied / pending / adjusted"


class ScenarioError(AssertionError):
    pass


class Api:
    """A thin client that signs requests as a named user."""

    def __init__(self, client):
        self.client, self.tokens, self.user_ids = client, {}, {}

    def login(self, username, password):
        r = self.client.post("/api/auth/login", json={"username": username, "password": password})
        if r.status_code == 200:
            self.tokens[username] = r.json()["token"]
            self.user_ids[username] = r.json()["user"]["id"]
        return r

    def call(self, method, user, path, **kw):
        headers = dict(kw.pop("headers", {}) or {})
        if user is not None:
            headers["Authorization"] = f"Bearer {self.tokens[user]}"
        return self.client.request(method, path, headers=headers, **kw)

    def get(self, user, path, **kw):
        return self.call("GET", user, path, **kw)

    def post(self, user, path, **kw):
        return self.call("POST", user, path, **kw)

    def put(self, user, path, **kw):
        return self.call("PUT", user, path, **kw)

    def patch(self, user, path, **kw):
        return self.call("PATCH", user, path, **kw)

    def ok(self, method, user, path, **kw):
        r = self.call(method, user, path, **kw)
        if r.status_code >= 300:
            raise ScenarioError(f"{method} {path} as {user} returned {r.status_code}: {r.text[:400]}")
        return r.json() if r.headers.get("content-type", "").startswith("application/json") else r


class Checks:
    def __init__(self, scenario, title):
        self.scenario, self.title, self.items = scenario, title, []

    def add(self, check_id, criterion, passed, actual, expected=""):
        self.items.append({"id": check_id, "criterion": criterion, "expected": expected, "actual": str(actual),
                           "passed": bool(passed)})

    def result(self, **extra):
        return {"scenario": self.scenario, "title": self.title, "checks": self.items,
                "passed": all(i["passed"] for i in self.items), **extra}


@contextlib.contextmanager
def ai_unavailable():
    """Simulate an AI outage by hiding the Gemini settings for the duration of the block."""
    saved = {k: os.environ.pop(k) for k in ("GEMINI_API_KEY", "GEMINI_MODEL") if k in os.environ}
    try:
        yield
    finally:
        os.environ.update(saved)


# --- shared steps ------------------------------------------------------------------------------------

def setup_team(api, password):
    for username, name, role in TEAM:
        r = api.post("admin", "/api/users", json={"username": username, "display_name": name, "role": role,
                                                  "password": password})
        if r.status_code not in (201, 409):
            raise ScenarioError(f"Creating {username} failed: {r.text}")
        api.login(username, password)


def new_client(api, analyst, code, name, team):
    c = api.ok("POST", analyst, "/api/clients", json={"code": code, "name": name, "go_live_target": "2027-01-15"})
    for u in team:
        api.ok("POST", "admin", f"/api/clients/{c['id']}/access", json={"user_id": api.user_ids[u]})
    return c


def upload(api, user, client_id, name, raw):
    return api.ok("POST", user, f"/api/clients/{client_id}/submissions", files={"file": (name, raw, "text/csv")})


def prepare_mapping(api, analyst, submission_id, overrides=None, use_ai=False):
    m = api.ok("POST", analyst, f"/api/submissions/{submission_id}/mappings", json={"use_ai": use_ai})
    chosen = {f: s["column"] for f, s in m["suggestions"].items()}
    chosen.update(overrides or {})
    confirmed = [f for f, s in m["suggestions"].items() if s["needs_confirmation"]]
    api.ok("PUT", analyst, f"/api/mappings/{m['id']}", json={"mapping": chosen, "confirmed_fields": confirmed,
                                                            "submit": True, "note": "Checked against the file."})
    return m


def approve_mapping(api, approver, mapping_id):
    return api.ok("POST", approver, f"/api/mappings/{mapping_id}/review",
                  json={"approve": True, "comment": "Checked the mapping against the client's file layout."})


def validate(api, analyst, submission_id):
    run = api.ok("POST", analyst, f"/api/submissions/{submission_id}/runs")
    return api.ok("GET", analyst, f"/api/runs/{run['id']}")


def onboard_file(api, analyst, approver, client_id, name, raw, overrides=synth.ANSWER_KEY):
    sub = upload(api, analyst, client_id, name, raw)["submission"]
    m = prepare_mapping(api, analyst, sub["id"], overrides)
    approve_mapping(api, approver, m["id"])
    return sub, m, validate(api, analyst, sub["id"])


def exceptions(api, user, client_id):
    return {(e["field"], e["rule"]): e for e in api.ok("GET", user, f"/api/clients/{client_id}/exceptions")}


def verify_evidence(content):
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        files = {n.split("/", 1)[1]: z.read(n) for n in z.namelist()}
    manifest = json.loads(files.pop("manifest.json"))
    return (set(manifest["files"]) == set(files)
            and all(hashlib.sha256(files[n]).hexdigest() == h for n, h in manifest["files"].items())), manifest


# --- scenarios ---------------------------------------------------------------------------------------

def scenario_a(api, ctx):
    ch = Checks("A", "Clean file: straight through to go-live and export")
    c = new_client(api, "ana", "A-ASTER", "Aster Health Plan (synthetic)", ["priya"])
    ctx["A"] = c["id"]
    raw, _ = build_file(rows=600, seed=11)
    sub, m, run = onboard_file(api, "ana", "priya", c["id"], "aster_claims_nov2026.csv", raw)
    ctx["A_run"] = run["id"]
    ch.add("A1", "A clean file is validated as Ready with no findings",
           run["decision"] == "Ready" and run["blockers"] == 0 and run["warnings"] == 0,
           f"{run['decision']}, {run['blockers']} blockers, {run['warnings']} warnings", "Ready, 0, 0")
    ready = api.ok("GET", "ana", f"/api/clients/{c['id']}/readiness")
    ch.add("A2", "Every readiness check passes before approval",
           ready["ready_for_approval"] and all(x["ok"] for x in ready["checks"]), ready["stage"], "Ready for approval")
    r = api.post("ana", f"/api/clients/{c['id']}/golive", json={"approve": True, "comment": "Looks fine"})
    ch.add("A3", "An analyst cannot approve go-live", r.status_code == 403, r.status_code, 403)
    api.ok("POST", "priya", f"/api/clients/{c['id']}/golive",
           json={"approve": True, "comment": "Clean file and every readiness check passes."})
    api.ok("POST", "ana", f"/api/clients/{c['id']}/exports")
    exp = api.ok("GET", "ana", f"/api/clients/{c['id']}/exports")[0]
    ds = api.ok("GET", "admin", f"/api/admin/downstream/{c['id']}")
    ch.add("A4", "The export loads every record exactly once",
           exp["status"] == "completed" and ds["records"] == 600 and ds["distinct_claim_ids"] == 600,
           f"{exp['status']}: {ds['records']} records, {ds['distinct_claim_ids']} distinct", "completed: 600, 600")
    ok, manifest = verify_evidence(api.get("priya", f"/api/clients/{c['id']}/evidence").content)
    ch.add("A5", "The evidence package's SHA-256 manifest matches every file", ok,
           f"{len(manifest['files'])} files, manifest {'matches' if ok else 'does not match'}")
    state = api.ok("GET", "ana", f"/api/clients/{c['id']}/readiness")
    ch.add("A6", "The client shows as Live after the export", state["stage"] == "Live", state["stage"], "Live")
    return ch.result()


def scenario_b(api, ctx):
    ch = Checks("B", "Poor-quality file: 2,000 rows with 52 planted errors")
    c = new_client(api, "ana", "B-BIRCH", "Birch Mutual (synthetic)", ["priya", "birch.contact"])
    ctx["B"] = c["id"]
    raw = (EXAMPLE / "client_claims.csv").read_bytes()
    key = json.loads((EXAMPLE / "answer_key.json").read_text(encoding="utf-8"))
    sub, m, run = onboard_file(api, "ana", "priya", c["id"], "birch_claims_extract.csv", raw)
    ctx["B_run"] = run["id"]
    ch.add("B1", "The file is Not ready, with the planted blockers and warnings counted",
           run["decision"] == "Not ready" and run["blockers"] == 42 and run["warnings"] == 10,
           f"{run['decision']}, {run['blockers']} blockers, {run['warnings']} warnings", "Not ready, 42, 10")
    findings = api.ok("GET", "ana", f"/api/runs/{run['id']}/findings", params={"limit": 1000})["items"]
    got = Counter((f["line"], f["field"], f["rule"]) for f in findings)
    want = Counter((p["line"], p["field"], p["rule"]) for p in key["planted_errors"])
    caught, false_alarms = sum((got & want).values()), sum((got - want).values())
    ctx["recall"] = {"planted": sum(want.values()), "caught": caught, "missed": sum((want - got).values()),
                     "false_alarms": false_alarms, "rows_checked": run["rows_checked"]}
    ch.add("B2", "Every planted error is found at the right line, with no false alarms",
           caught == 52 and false_alarms == 0, f"{caught} of 52 found, {false_alarms} false alarms", "52 of 52, 0")
    exc = exceptions(api, "ana", c["id"])
    ch.add("B3", "One exception is opened per rule group, each with severity and status",
           len(exc) == 14 and all(e["status"] == "open" for e in exc.values()),
           f"{len(exc)} groups, statuses {sorted({e['status'] for e in exc.values()})}", "14 open groups")
    r = api.post("priya", f"/api/clients/{c['id']}/golive", json={"approve": True, "comment": "Try"})
    ch.add("B4", "Go-live cannot be approved while blockers remain", r.status_code == 409, r.status_code, 409)
    blocker = exc[("provider_npi", "exactly 10 digits")]
    r = api.patch("priya", f"/api/exceptions/{blocker['id']}",
                  json={"status": "accepted", "note": "Client says these are fine."})
    ch.add("B5", "A blocker cannot be accepted or waived", r.status_code == 409, r.status_code, 409)
    warning = exc[("place_of_service", "exactly 2 digits")]
    api.ok("PATCH", "ana", f"/api/exceptions/{warning['id']}", json={"owner_id": api.user_ids["ana"],
                                                                   "status": "in_progress"})
    r = api.patch("priya", f"/api/exceptions/{warning['id']}",
                  json={"status": "accepted", "note": "Client confirmed POS 110 is a legacy code mapped downstream."})
    events = api.ok("GET", "priya", f"/api/exceptions/{warning['id']}")["events"]
    ch.add("B6", "A warning can be accepted by an approver with a note, and the change is recorded",
           r.status_code == 200 and r.json()["status"] == "accepted" and len(events) >= 3,
           f"{r.status_code}, {len(events)} events")
    r = api.patch("ana", f"/api/exceptions/{blocker['id']}", json={"status": "resolved", "note": "done"})
    ch.add("B7", "Nobody can mark an exception resolved by hand", r.status_code == 409, r.status_code, 409)
    before = api.ok("GET", "birch.contact", f"/api/clients/{c['id']}/communications")
    letter = api.ok("POST", "ana", f"/api/clients/{c['id']}/communications", json={"kind": "issue_letter"})
    api.ok("POST", "ana", f"/api/communications/{letter['id']}/send")
    after = api.ok("GET", "birch.contact", f"/api/clients/{c['id']}/communications")
    body = api.ok("GET", "birch.contact", f"/api/communications/{letter['id']}")["body"]
    ch.add("B8", "The client sees the issue letter only once sent, written with their own column names",
           len(before) == 0 and len(after) == 1 and "Rendering NPI" in body and "provider_npi" not in body,
           f"{len(before)} before, {len(after)} after sending; client column names used: {'Rendering NPI' in body}")
    with ai_unavailable():
        ex = api.ok("GET", "ana", f"/api/exceptions/{blocker['id']}/explanation", params={"ai": "true"})
    ch.add("B9", "A rule-based explanation is always available, even when AI is unavailable",
           ex["source"] == "rules" and "6 rows" in ex["summary"] and ex["ai_error"] is not None,
           ex["summary"][:90])
    return ch.result()


def scenario_c(api, ctx):
    ch = Checks("C", "Different schema with ambiguous mappings and a rule change")
    c = new_client(api, "ana", "C-CEDAR", "Cedar Benefits (synthetic)", ["priya"])
    ctx["C"] = c["id"]
    raw, _ = build_file(rows=800, seed=23, rename=VENDOR_C, us_dates=True)
    sub = upload(api, "ana", c["id"], "cedar_vendor_layout.csv", raw)["submission"]
    m = api.ok("POST", "ana", f"/api/submissions/{sub['id']}/mappings", json={"use_ai": False})
    s = m["suggestions"]
    flagged = {f: x["level"] for f, x in s.items() if x["needs_confirmation"]}
    ch.add("C1", "Ambiguous, low-confidence and missing suggestions are flagged, not hidden",
           s["provider_npi"]["level"] == "ambiguous" and s["diagnosis_code"]["level"] == "none"
           and s["procedure_code"]["needs_confirmation"] and s["claim_status"]["needs_confirmation"], flagged)
    r = api.put("ana", f"/api/mappings/{m['id']}", json={"mapping": {f: x["column"] for f, x in s.items()},
                                                         "confirmed_fields": [], "submit": True})
    detail = r.json().get("detail", {}) if r.status_code == 422 else {}
    ch.add("C2", "A mapping with unconfirmed ambiguous or missing fields cannot be submitted",
           r.status_code == 422 and "provider_npi" in detail.get("unconfirmed_fields", []),
           f"{r.status_code}: unconfirmed {detail.get('unconfirmed_fields')}", 422)
    api.ok("PUT", "ana", f"/api/mappings/{m['id']}", json={
        "mapping": VENDOR_C_MAPPING, "confirmed_fields": list(flagged), "submit": True,
        "note": "Servicing Provider NPI is the rendering NPI per the vendor's data dictionary."})
    saved = api.ok("GET", "ana", f"/api/mappings/{m['id']}")
    npi = next((x for x in saved["corrections"] if x["field"] == "provider_npi"), {})
    ch.add("C3", "The analyst's correction of the suggested NPI column is logged",
           npi.get("suggested_column") == "Billing Provider NPI" and npi.get("chosen_column") == "Servicing Provider NPI",
           npi)
    r = api.post("ana", f"/api/mappings/{m['id']}/review", json={"approve": True, "comment": "Self-approve"})
    ch.add("C4", "The analyst who prepared a mapping cannot approve it", r.status_code == 403, r.status_code, 403)
    approve_mapping(api, "priya", m["id"])
    run1 = validate(api, "ana", sub["id"])
    ch.add("C5", "With the baseline rules, the vendor's MM/DD/YYYY dates are blockers",
           run1["decision"] == "Not ready" and run1["blockers"] >= 1600, f"{run1['decision']}, {run1['blockers']} blockers")
    baseline = api.ok("GET", "ana", "/api/rules/baseline").text
    rs = api.ok("POST", "ana", f"/api/clients/{c['id']}/rulesets", json={
        "text": rules_with_us_dates(baseline), "note": "Cedar sends US-format dates (confirmed in kickoff)."})
    api.ok("POST", "priya", f"/api/rulesets/{rs['id']}/review", json={"approve": True, "comment": "Agreed."})
    sets = api.ok("GET", "priya", f"/api/clients/{c['id']}/rulesets")
    state = api.ok("GET", "ana", f"/api/clients/{c['id']}/readiness")
    validated = next(x["ok"] for x in state["checks"] if x["key"] == "validated")
    ch.add("C6", "The rule change is a new approved version, and it invalidates the earlier validation",
           [(x["version"], x["status"]) for x in sets] == [(2, "approved"), (1, "superseded")] and not validated,
           [(x["version"], x["status"]) for x in sets])
    run2 = validate(api, "ana", sub["id"])
    ch.add("C7", "Re-validated under the approved rules, the file is Ready",
           run2["decision"] == "Ready", f"{run2['decision']}, {run2['blockers']} blockers")
    trail = api.ok("GET", "priya", f"/api/clients/{c['id']}/audit")
    drafted = next((a for a in trail if a["action"] == "ruleset.drafted"), {})
    ch.add("C8", "The configuration change is traceable: who drafted, what changed, who approved",
           drafted.get("actor") == "ana" and drafted["detail"]["changes"]["changed"] == ["member_dob", "service_date"]
           and any(a["action"] == "ruleset.approved" and a["actor"] == "priya" for a in trail),
           drafted.get("detail", {}).get("changes"))
    api.ok("POST", "ana", f"/api/mappings/{m['id']}/template", json={"name": "Cedar vendor extract layout"})
    c2 = new_client(api, "ana", "C2-CEDAR-WEST", "Cedar West (synthetic)", ["priya"])
    raw2, _ = build_file(rows=50, seed=24, rename=VENDOR_C, us_dates=True, first_claim=5000)
    sub2 = upload(api, "ana", c2["id"], "cedar_west.csv", raw2)["submission"]
    m2 = api.ok("POST", "ana", f"/api/submissions/{sub2['id']}/mappings", json={"use_ai": False})
    reused = {f: x["column"] for f, x in m2["suggestions"].items()} == VENDOR_C_MAPPING
    ch.add("C9", "A saved template is reused for the same layout with high confidence",
           reused and m2["template"] == "Cedar vendor extract layout"
           and all(x["level"] == "high" for x in m2["suggestions"].values()), m2["template"])
    return ch.result()


D_FILES = [
    [("provider_npi", "exactly 10 digits", 6), ("claim_status", STATUS_RULE, 3),
     ("paid_amount", "not greater than billed_amount", 4), ("place_of_service", "exactly 2 digits", 5)],
    [("paid_amount", "not greater than billed_amount", 2), ("place_of_service", "exactly 2 digits", 5),
     ("member_dob", "future", 2)],
    [("provider_npi", "exactly 10 digits", 1)],
    [],
]


def scenario_d(api, ctx):
    ch = Checks("D", "Multiple resubmissions: fixed, unresolved, new and regressed problems")
    c = new_client(api, "sam", "D-DOGWOOD", "Dogwood Health (synthetic)", ["priya", "omar"])
    ctx["D"] = c["id"]
    files = [build_file(rows=700, seed=31, breaks=b)[0] for b in D_FILES]
    sub, m, run = onboard_file(api, "sam", "priya", c["id"], "dogwood_round1.csv", files[0])
    first = exceptions(api, "sam", c["id"])
    sub2 = upload(api, "sam", c["id"], "dogwood_round2.csv", files[1])["submission"]
    validate(api, "sam", sub2["id"])
    history = api.ok("GET", "sam", f"/api/clients/{c['id']}/resubmissions")
    comp = history[1]["comparison"]
    names = {k: sorted(f"{r['field']}: {r['rule']}" for r in comp[k]) for k in ("fixed", "new", "unresolved")}
    ch.add("D1", "Resubmission 2 is compared with 1: fixed, new and still-unresolved problems",
           names == {"fixed": [f"claim_status: {STATUS_RULE}", "provider_npi: exactly 10 digits"],
                     "new": ["member_dob: not in the future", "service_date: not before member_dob"],
                     "unresolved": ["paid_amount: not greater than billed_amount", "place_of_service: exactly 2 digits"]},
           names)
    exc = exceptions(api, "sam", c["id"])
    npi = exc[("provider_npi", "exactly 10 digits")]
    ch.add("D2", "Exceptions absent from the resubmission are resolved automatically",
           len(first) == 4 and npi["status"] == "resolved" and exc[("claim_status", STATUS_RULE)]["status"] == "resolved",
           f"NPI {npi['status']}: {npi['resolution']}")
    sub3 = upload(api, "sam", c["id"], "dogwood_round3.csv", files[2])["submission"]
    validate(api, "sam", sub3["id"])
    exc = exceptions(api, "sam", c["id"])
    npi = exc[("provider_npi", "exactly 10 digits")]
    events = [e["kind"] for e in api.ok("GET", "sam", f"/api/exceptions/{npi['id']}")["events"]]
    ch.add("D3", "A problem that comes back is reopened, with its history kept",
           npi["status"] == "reopened" and events == ["created", "auto_resolved", "reopened"], events)
    r = api.post("priya", f"/api/clients/{c['id']}/golive", json={"approve": True, "comment": "Try"})
    sub4 = upload(api, "sam", c["id"], "dogwood_round4.csv", files[3])["submission"]
    run4 = validate(api, "sam", sub4["id"])
    state = api.ok("GET", "sam", f"/api/clients/{c['id']}/readiness")
    open_left = [e for e in exceptions(api, "sam", c["id"]).values() if e["status"] != "resolved"]
    ch.add("D4", "Ready only after a file with no blockers, with every exception resolved",
           r.status_code == 409 and run4["decision"] == "Ready" and state["ready_for_approval"] and not open_left,
           f"round 3 approval {r.status_code}; round 4 {run4['decision']}, {len(open_left)} open")
    card = api.ok("GET", "priya", f"/api/clients/{c['id']}/scorecard")
    ch.add("D5", "The scorecard reports rounds to acceptance and rework from the records",
           card["rounds_to_acceptance"] == 4 and card["first_pass_acceptance"] is False and card["rework_rate"] == 0.75,
           f"rounds {card['rounds_to_acceptance']}, first pass {card['first_pass_acceptance']}, rework {card['rework_rate']}")
    api.ok("POST", "omar", f"/api/clients/{c['id']}/golive", json={"approve": True, "comment": "Round 4 clean."})
    return ch.result()


def scenario_e(api, ctx):
    ch = Checks("E", "Operational failure: duplicates, failed and interrupted runs, bad files, downstream outage")
    c = new_client(api, "ana", "E-ELM", "Elm Street Cooperative (synthetic)", ["priya"])
    ctx["E"] = c["id"]
    raw, _ = build_file(rows=1500, seed=41)
    first = upload(api, "ana", c["id"], "elm_claims.csv", raw)
    again = upload(api, "ana", c["id"], "elm_claims (1).csv", raw)
    subs = api.ok("GET", "ana", f"/api/clients/{c['id']}/submissions")
    ch.add("E1", "Uploading the same file twice stores it once", again["duplicate"] and
           again["submission"]["id"] == first["submission"]["id"] and len(subs) == 1,
           f"duplicate={again['duplicate']}, {len(subs)} submission(s)")
    sub = first["submission"]
    with ai_unavailable():
        m = api.ok("POST", "ana", f"/api/submissions/{sub['id']}/mappings", json={"use_ai": True})
    ch.add("E2", "When AI is unavailable, mapping falls back to name matching and says so",
           m["ai_used"] is False and m["ai_error"] and m["suggestions"]["claim_id"]["column"] == "Clm_Nbr",
           (m["ai_error"] or "")[:80])
    chosen = {f: x["column"] for f, x in m["suggestions"].items()} | synth.ANSWER_KEY
    api.ok("PUT", "ana", f"/api/mappings/{m['id']}", json={"mapping": chosen, "submit": True, "confirmed_fields":
                                                          [f for f, x in m["suggestions"].items() if x["needs_confirmation"]]})
    approve_mapping(api, "priya", m["id"])
    api.ok("PUT", "admin", "/api/admin/simulation", json={"fail_next_run": True})
    failed = validate(api, "ana", sub["id"])
    api.ok("POST", "ana", f"/api/runs/{failed['id']}/retry")
    retried = api.ok("GET", "ana", f"/api/runs/{failed['id']}")
    ch.add("E3", "A failed run is recorded and a retry completes with the full result",
           failed["status"] == "failed" and retried["status"] == "completed" and retried["attempts"] == 2
           and retried["rows_checked"] == 1500 and retried["decision"] == "Ready",
           f"{failed['status']} -> {retried['status']} after {retried['attempts']} attempts")
    api.ok("PUT", "admin", "/api/admin/simulation", json={"hold_next_run": True})
    held = validate(api, "ana", sub["id"])
    recovered = api.ok("POST", "admin", "/api/admin/recover")
    after = api.ok("GET", "ana", f"/api/runs/{held['id']}")
    api.ok("POST", "ana", f"/api/runs/{held['id']}/retry")
    done = api.ok("GET", "ana", f"/api/runs/{held['id']}")
    ch.add("E4", "A run interrupted mid-processing is marked interrupted on recovery and retried without loss",
           held["status"] == "running" and after["status"] == "interrupted" and recovered["runs"] == 1
           and done["status"] == "completed" and done["rows_checked"] == 1500,
           f"{held['status']} -> {after['status']} -> {done['status']}")
    cut = upload(api, "ana", c["id"], "elm_claims_partial.csv", truncated(raw))["submission"]
    run_cut = validate(api, "ana", cut["id"])
    rows = api.ok("GET", "ana", f"/api/runs/{run_cut['id']}/findings", params={"field": "(row)"})
    ch.add("E5", "A file cut off mid-row is caught as a blocker on the broken row",
           run_cut["decision"] == "Not ready" and rows["total"] == 1, f"{run_cut['decision']}, {rows['total']} broken row")
    bad = upload(api, "ana", c["id"], "elm_claims_bad_encoding.csv", corrupted(raw))["submission"]
    run_bad = validate(api, "ana", bad["id"])
    exc = exceptions(api, "ana", c["id"])
    state = api.ok("GET", "ana", f"/api/clients/{c['id']}/readiness")
    ch.add("E6", "A file that cannot be read to the end is never ready, and nothing is cleared by the partial scan",
           run_bad["scan_complete"] is False and ("(file)", "file must be read completely") in exc
           and exc[("(row)", "correct number of fields")]["status"] == "open" and not state["ready_for_approval"],
           f"scan_complete={run_bad['scan_complete']}, stage {state['stage']}")
    fixed = upload(api, "ana", c["id"], "elm_claims_resent.csv", raw)
    run_ok = validate(api, "ana", fixed["submission"]["id"])
    exc = exceptions(api, "ana", c["id"])
    ch.add("E7", "Re-sending the good file recovers: Ready, and the file-level problems resolve",
           not fixed["duplicate"] and run_ok["decision"] == "Ready" and all(e["status"] == "resolved" for e in exc.values()),
           f"submission #{fixed['submission']['sequence']} {run_ok['decision']}")
    api.ok("POST", "priya", f"/api/clients/{c['id']}/golive", json={"approve": True, "comment": "Resent file clean."})
    api.ok("PUT", "admin", "/api/admin/simulation",
           json={"downstream_fault": {"mode": "outage", "from_batch": 1, "remaining": 3}})
    exp = api.ok("POST", "ana", f"/api/clients/{c['id']}/exports")
    exp = api.ok("GET", "ana", f"/api/clients/{c['id']}/exports")[0]
    ch.add("E8", "A downstream outage fails the export cleanly, keeping the batches already delivered",
           exp["status"] == "failed" and exp["batches_done"] == 1 and exp["sent_records"] > 0,
           f"{exp['status']} after {exp['batches_done']} of {exp['batches_total']} batches: {exp['last_error'][:70]}")
    api.ok("PUT", "admin", "/api/admin/simulation", json={"downstream_fault": {"mode": "lost_ack", "batches": [1]}})
    api.ok("POST", "ana", f"/api/exports/{exp['id']}/retry")
    exp = api.ok("GET", "ana", f"/api/clients/{c['id']}/exports")[0]
    ds = api.ok("GET", "admin", f"/api/admin/downstream/{c['id']}")
    ch.add("E9", "The resumed export, with a lost acknowledgement, loads every claim exactly once",
           exp["status"] == "completed" and ds["records"] == 1500 and ds["distinct_claim_ids"] == 1500
           and exp["sent_records"] == 1500 and exp["batch_retries"] >= 1,
           f"{exp['status']}: {ds['records']} records, {ds['distinct_claim_ids']} distinct, {exp['batch_retries']} batch retries")
    again = api.ok("POST", "ana", f"/api/clients/{c['id']}/exports")
    ds2 = api.ok("GET", "admin", f"/api/admin/downstream/{c['id']}")
    ch.add("E10", "Asking to export again returns the same export and loads nothing twice",
           again["existing"] and again["id"] == exp["id"] and ds2["records"] == 1500,
           f"existing={again['existing']}, {ds2['records']} records")
    api.ok("PUT", "admin", "/api/admin/simulation", json={})
    return ch.result()


def scenario_f(api, ctx, password):
    ch = Checks("F", "Security boundaries: client separation, roles, sessions and audit")
    f = new_client(api, "sam", "F-FIR", "Fir Valley Plan (synthetic)", ["priya", "fir.contact"])
    ctx["F"] = f["id"]
    visible = [x["code"] for x in api.ok("GET", "birch.contact", "/api/clients")]
    ch.add("F1", "A client contact sees only their own client", visible == ["B-BIRCH"], visible, ["B-BIRCH"])
    probes = [f"/api/clients/{ctx['A']}", f"/api/runs/{ctx['A_run']}", f"/api/runs/{ctx['A_run']}/findings.csv",
              f"/api/clients/{ctx['E']}/exceptions", f"/api/clients/{ctx['A']}/resubmissions"]
    codes = [api.get("birch.contact", p).status_code for p in probes]
    ch.add("F2", "Another client's records look exactly like records that do not exist (404)",
           set(codes) == {404}, codes)
    codes = [api.get("sam", f"/api/clients/{ctx['A']}").status_code,
             api.post("sam", f"/api/clients/{ctx['A']}/submissions",
                      files={"file": ("x.csv", b"a,b\n1,2\n", "text/csv")}).status_code]
    ch.add("F3", "An analyst without access to a client cannot read or upload to it", codes == [404, 404], codes)
    b = ctx["B"]
    exc_id = next(iter(exceptions(api, "ana", b).values()))["id"]
    codes = {
        "approve go-live": api.post("birch.contact", f"/api/clients/{b}/golive",
                                    json={"approve": True, "comment": "x"}).status_code,
        "change exception status": api.patch("birch.contact", f"/api/exceptions/{exc_id}",
                                             json={"status": "in_progress"}).status_code,
        "read audit": api.get("birch.contact", f"/api/clients/{b}/audit").status_code,
        "download evidence": api.get("birch.contact", f"/api/clients/{b}/evidence").status_code,
        "read mappings": api.get("birch.contact", f"/api/clients/{b}/mappings").status_code,
    }
    note = api.patch("birch.contact", f"/api/exceptions/{exc_id}",
                     json={"note": "We are correcting the NPIs in our source system."}).status_code
    ch.add("F4", "A client contact cannot approve, change status, or read audit and evidence, but can add notes",
           set(codes.values()) == {403} and note == 200, {**codes, "add note": note})
    codes = [api.client.get(f"/api/clients/{b}").status_code,
             api.client.get(f"/api/clients/{b}", headers={"Authorization": "Bearer not-a-real-token"}).status_code]
    ch.add("F5", "Requests without a valid session are refused (401)", codes == [401, 401], codes)
    attempts = [api.client.post("/api/auth/login", json={"username": "fir.contact", "password": "wrong-password-1"}
                                ).status_code for _ in range(5)]
    locked = api.client.post("/api/auth/login", json={"username": "fir.contact", "password": password}).status_code
    api.ok("PATCH", "admin", f"/api/users/{api.user_ids['fir.contact']}", json={"unlock": True})
    unlocked = api.login("fir.contact", password).status_code
    ch.add("F6", "Five wrong passwords lock the account, even against the right password, until unlocked",
           attempts == [401] * 5 and locked == 423 and unlocked == 200, f"{attempts} then {locked}; after unlock {unlocked}")
    baseline = api.ok("GET", "admin", "/api/rules/baseline").text
    rs = api.ok("POST", "admin", f"/api/clients/{f['id']}/rulesets", json={
        "text": baseline.replace("exactly 2 digits (warning)", "exactly 2 digits"), "note": "Make POS a blocker."})
    own = api.post("admin", f"/api/rulesets/{rs['id']}/review", json={"approve": True, "comment": "mine"}).status_code
    ch.add("F7", "Nobody approves their own change, not even an administrator (four-eyes)", own == 403, own, 403)
    api.login("omar", password)
    api.ok("POST", "omar", "/api/auth/logout")
    after = api.get("omar", "/api/auth/me").status_code
    ch.add("F8", "Signing out ends the session", after == 401, after, 401)
    weak = api.post("admin", "/api/users", json={"username": "weak.user", "display_name": "Weak", "role": "approver",
                                                 "password": "short"}).status_code
    ch.add("F9", "Weak passwords are refused", weak == 422, weak, 422)
    chain = api.ok("GET", "admin", "/api/audit/verify")
    ch.add("F10", "The hash-chained audit trail verifies end to end", chain["ok"], f"{chain['entries']} entries")
    return ch.result()


def performance(api, rows=100_000):
    """The largest file the platform accepts: upload, validate and export, timed."""
    c = new_client(api, "ana", "P-PERF", "Performance check (synthetic)", ["priya"])
    raw, _ = build_file(rows=rows, seed=99)
    t0 = time.perf_counter()
    sub = upload(api, "ana", c["id"], "large_extract.csv", raw)["submission"]
    upload_s = time.perf_counter() - t0
    m = prepare_mapping(api, "ana", sub["id"], synth.ANSWER_KEY)
    approve_mapping(api, "priya", m["id"])
    run = validate(api, "ana", sub["id"])
    api.ok("POST", "priya", f"/api/clients/{c['id']}/golive", json={"approve": True, "comment": "Performance run."})
    api.ok("POST", "ana", f"/api/clients/{c['id']}/exports")
    exp = api.ok("GET", "ana", f"/api/clients/{c['id']}/exports")[0]
    ds = api.ok("GET", "admin", f"/api/admin/downstream/{c['id']}")
    return {"rows": rows, "file_mb": round(len(raw) / 1e6, 1), "upload_seconds": round(upload_s, 2),
            "validation_seconds": round(run["duration_ms"] / 1000, 2),
            "validation_rows_per_second": round(rows / (run["duration_ms"] / 1000)),
            "decision": run["decision"], "export_status": exp["status"],
            "export_seconds": round(exp["duration_ms"] / 1000, 2), "export_batches": exp["batches_total"],
            "records_loaded": ds["records"], "distinct_claim_ids": ds["distinct_claim_ids"]}


def run_all(client, admin_password, password, include_performance=False, perf_rows=100_000):
    api = Api(client)
    if api.login("admin", admin_password).status_code != 200:
        raise ScenarioError("The admin account could not sign in.")
    setup_team(api, password)
    ctx = {}
    results = [scenario_a(api, ctx), scenario_b(api, ctx), scenario_c(api, ctx), scenario_d(api, ctx),
               scenario_e(api, ctx), scenario_f(api, ctx, password)]
    out = {"scenarios": results, "planted_error_recall": ctx.get("recall"),
           "portfolio_kpis": api.ok("GET", "priya", "/api/reports/portfolio")["kpis"],
           "processing": api.ok("GET", "admin", "/api/metrics/processing")["runs"]}
    if include_performance:
        out["performance"] = performance(api, perf_rows)
    out["checks_passed"] = sum(i["passed"] for r in results for i in r["checks"])
    out["checks_total"] = sum(len(r["checks"]) for r in results)
    return out, ctx
