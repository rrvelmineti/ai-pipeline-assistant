"""Clients, versioned rules, mapping approval, readiness and the go-live approval.

Every decision that matters is made by a person with the right role and is written to the audit trail.
Approvals follow the four-eyes principle: nobody approves their own work.
"""
from fastapi import HTTPException
from sqlalchemy import func, select

from claims_onboarding.rules import BLOCKER, RULES_PATH, RulesError, parse_rules

from . import audit
from .db import utcnow
from .models import (Approval, Client, ClientAccess, ExceptionItem, Export, Mapping, MappingTemplate, Milestone,
                     RuleSet, Submission, ValidationRun)

OPEN_STATES = ("open", "in_progress", "reopened")
DEFAULT_MILESTONES = [
    ("kickoff", "Kickoff and first file received"),
    ("rules_confirmed", "Onboarding rules confirmed"),
    ("mapping_approved", "Column mapping approved"),
    ("first_validation", "First file validated"),
    ("exceptions_cleared", "Blocker exceptions cleared"),
    ("go_live_approved", "Go-live approved"),
    ("production_export", "Records loaded downstream"),
]


# --- lookups -----------------------------------------------------------------------------------------

def current_rule_set(db, client_id):
    return db.execute(select(RuleSet).where(RuleSet.client_id == client_id, RuleSet.status == "approved")
                      .order_by(RuleSet.version.desc())).scalars().first()


def current_mapping(db, client_id):
    return db.execute(select(Mapping).where(Mapping.client_id == client_id, Mapping.status == "approved")
                      .order_by(Mapping.version.desc())).scalars().first()


def latest_submission(db, client_id):
    return db.execute(select(Submission).where(Submission.client_id == client_id)
                      .order_by(Submission.sequence.desc())).scalars().first()


def latest_run(db, submission_id, completed_only=False):
    q = select(ValidationRun).where(ValidationRun.submission_id == submission_id)
    if completed_only:
        q = q.where(ValidationRun.status == "completed")
    return db.execute(q.order_by(ValidationRun.id.desc())).scalars().first()


def complete_milestone(db, client_id, key):
    m = db.execute(select(Milestone).where(Milestone.client_id == client_id, Milestone.key == key)).scalar_one_or_none()
    if m is not None and m.status != "done":
        m.status, m.completed_at = "done", utcnow()


# --- clients -----------------------------------------------------------------------------------------

def create_client(db, user, code, name, go_live_target=None):
    if db.execute(select(Client.id).where(Client.code == code)).first():
        raise HTTPException(409, f"A client with code '{code}' already exists.")
    client = Client(code=code, name=name, go_live_target=go_live_target, created_by=user.id)
    db.add(client)
    db.flush()
    if user.role != "admin":
        db.add(ClientAccess(user_id=user.id, client_id=client.id))
    db.add(RuleSet(client_id=client.id, version=1, text=RULES_PATH.read_text(encoding="utf-8"), status="approved",
                   note="Platform baseline rules (claims_onboarding/rules.txt).", approved_at=utcnow()))
    for i, (key, label) in enumerate(DEFAULT_MILESTONES):
        db.add(Milestone(client_id=client.id, key=key, name=label, sort=i))
    audit.record(db, user, "client.created", client_id=client.id, entity="client", entity_id=client.id,
                 detail={"code": code, "name": name, "baseline_rules": "claims_onboarding/rules.txt"})
    return client


# --- rules -------------------------------------------------------------------------------------------

def _rule_diff(old_text, new_text):
    old, new = parse_rules(old_text), parse_rules(new_text)
    changed = [f for f in set(old) & set(new) if [r.text for r in old[f].rules] != [r.text for r in new[f].rules]]
    return {"added": sorted(set(new) - set(old)), "removed": sorted(set(old) - set(new)), "changed": sorted(changed)}


def draft_rule_set(db, client, user, text, note):
    try:
        parse_rules(text)
    except RulesError as exc:
        raise HTTPException(422, str(exc)) from None
    current = current_rule_set(db, client.id)
    version = (db.execute(select(func.max(RuleSet.version)).where(RuleSet.client_id == client.id)).scalar() or 0) + 1
    rs = RuleSet(client_id=client.id, version=version, text=text, status="draft", note=note[:500], author_id=user.id)
    db.add(rs)
    db.flush()
    diff = _rule_diff(current.text, text) if current else {}
    audit.record(db, user, "ruleset.drafted", client_id=client.id, entity="ruleset", entity_id=rs.id,
                 detail={"version": version, "note": note[:500], "changes": diff})
    return rs


def review_rule_set(db, rs, user, approve, comment):
    if rs.status != "draft":
        raise HTTPException(409, f"Only draft rule sets can be reviewed; this one is {rs.status}.")
    if rs.author_id == user.id:
        raise HTTPException(403, "Rule changes need a second person: you cannot approve your own draft.")
    if approve:
        previous = current_rule_set(db, rs.client_id)
        if previous is not None:
            previous.status = "superseded"
        rs.status, rs.approver_id, rs.approved_at = "approved", user.id, utcnow()
        complete_milestone(db, rs.client_id, "rules_confirmed")
    else:
        if not comment.strip():
            raise HTTPException(422, "Say why the rule change is rejected.")
        rs.status, rs.approver_id = "rejected", user.id
    audit.record(db, user, "ruleset.approved" if approve else "ruleset.rejected", client_id=rs.client_id,
                 entity="ruleset", entity_id=rs.id, detail={"version": rs.version, "comment": comment[:500]})
    return rs


# --- mappings ----------------------------------------------------------------------------------------

def start_mapping(db, client, user, submission, result):
    """Store the suggestions shown to the analyst, so corrections are measured against what was really shown."""
    for old in db.execute(select(Mapping).where(Mapping.client_id == client.id,
                                                Mapping.status.in_(("draft", "rejected")))).scalars():
        old.status = "discarded"
    version = (db.execute(select(func.max(Mapping.version)).where(Mapping.client_id == client.id)).scalar() or 0) + 1
    sugg = result["suggestions"]
    m = Mapping(client_id=client.id, version=version, submission_id=submission.id, headers=list(submission.headers),
                suggestions=sugg, mapping={f: s["column"] for f, s in sugg.items()}, confirmed_fields=[],
                corrections=[], status="draft", author_id=user.id)
    db.add(m)
    db.flush()
    levels = {}
    for s in sugg.values():
        levels[s["level"]] = levels.get(s["level"], 0) + 1
    audit.record(db, user, "mapping.suggested", client_id=client.id, entity="mapping", entity_id=m.id,
                 detail={"version": version, "submission": submission.sequence, "levels": levels,
                         "ai_used": result["ai_used"], "ai_error": result["ai_error"], "template": result["template"]})
    return m


def review_mapping(db, m, user, approve, comment):
    if m.status != "pending_approval":
        raise HTTPException(409, f"Only mappings waiting for approval can be reviewed; this one is {m.status}.")
    if m.author_id == user.id:
        raise HTTPException(403, "Mappings need a second person: you cannot approve a mapping you prepared.")
    if approve:
        previous = current_mapping(db, m.client_id)
        if previous is not None:
            previous.status = "superseded"
        m.status, m.approver_id, m.approved_at, m.review_comment = "approved", user.id, utcnow(), comment[:500]
        complete_milestone(db, m.client_id, "mapping_approved")
    else:
        if not comment.strip():
            raise HTTPException(422, "Say what needs to change in the mapping.")
        m.status, m.approver_id, m.review_comment = "rejected", user.id, comment[:500]
    audit.record(db, user, "mapping.approved" if approve else "mapping.rejected", client_id=m.client_id,
                 entity="mapping", entity_id=m.id, detail={"version": m.version, "comment": comment[:500]})
    return m


def save_template(db, m, user, name):
    if m.status not in ("approved", "superseded"):
        raise HTTPException(409, "Only an approved mapping can be saved as a template.")
    if db.execute(select(MappingTemplate.id).where(MappingTemplate.name == name)).first():
        raise HTTPException(409, f"A template named '{name}' already exists.")
    t = MappingTemplate(name=name, headers=list(m.headers), mapping=dict(m.mapping), created_by=user.id)
    db.add(t)
    db.flush()
    audit.record(db, user, "template.saved", client_id=m.client_id, entity="template", entity_id=t.id,
                 detail={"name": name, "from_mapping_version": m.version})
    return t


# --- readiness and approval --------------------------------------------------------------------------

def client_state(db, client):
    """The readiness checklist. Ready for approval only when every check passes: never with open blockers."""
    rs, mp = current_rule_set(db, client.id), current_mapping(db, client.id)
    sub = latest_submission(db, client.id)
    run = latest_run(db, sub.id) if sub else None
    done = latest_run(db, sub.id, completed_only=True) if sub else None
    counts = dict(db.execute(select(ExceptionItem.severity, func.count(ExceptionItem.id)).where(
        ExceptionItem.client_id == client.id, ExceptionItem.status.in_(OPEN_STATES))
        .group_by(ExceptionItem.severity)).all())
    open_blockers, open_warnings = counts.get(BLOCKER, 0), sum(v for k, v in counts.items() if k != BLOCKER)
    current = bool(done and rs and mp and done.mapping_id == mp.id and done.rule_set_id == rs.id)
    checks = [
        ("rules_approved", "Onboarding rules approved", rs is not None),
        ("mapping_approved", "Column mapping approved", mp is not None),
        ("file_received", "Client file received", sub is not None),
        ("validated", "Latest file validated with the current mapping and rules", current),
        ("scan_complete", "Every row of the latest file was read", bool(done and done.scan_complete)),
        ("no_blockers", "No blocker findings in the latest file", bool(done and done.scan_complete and done.blockers == 0)),
        ("no_open_blockers", "No open blocker exceptions", open_blockers == 0),
        ("warnings_dispositioned", "Every warning resolved, or accepted with a note", open_warnings == 0),
    ]
    ready = all(ok for _, _, ok in checks)
    approval = None
    if done is not None:
        approval = db.execute(select(Approval).where(Approval.run_id == done.id, Approval.active.is_(True))
                              .order_by(Approval.id.desc())).scalars().first()
    export = db.execute(select(Export).where(Export.run_id == done.id)).scalar_one_or_none() if done else None
    if export is not None and export.status == "completed":
        stage = "Live"
    elif approval is not None and approval.decision == "approved":
        stage = "Approved"
    elif ready:
        stage = "Ready for approval"
    elif done is not None:
        stage = "Remediation"
    elif mp is not None and sub is not None:
        stage = "Validation"
    elif sub is not None:
        stage = "Mapping"
    else:
        stage = "Setup"
    return {
        "stage": stage, "ready_for_approval": ready,
        "checks": [{"key": k, "label": label, "ok": ok} for k, label, ok in checks],
        "open_blockers": open_blockers, "open_warnings": open_warnings,
        "rule_set_version": rs.version if rs else None, "mapping_version": mp.version if mp else None,
        "latest_submission": sub.sequence if sub else None,
        "run": done, "latest_run_status": run.status if run else None, "approval": approval, "export": export,
    }


def decide_go_live(db, client, user, approve, comment):
    state = client_state(db, client)
    run = state["run"]
    if run is None:
        raise HTTPException(409, "There is no completed validation to approve.")
    if approve and not state["ready_for_approval"]:
        failing = [c["label"] for c in state["checks"] if not c["ok"]]
        raise HTTPException(409, "Not ready for go-live: " + "; ".join(failing) + ".")
    if not comment.strip() and not approve:
        raise HTTPException(422, "Say why go-live is rejected.")
    mapping = db.get(Mapping, run.mapping_id)
    if approve and user.id in {mapping.author_id, run.created_by}:
        raise HTTPException(403, "Go-live needs an independent approver: you prepared the mapping or ran the "
                                 "validation for this file.")
    for old in db.execute(select(Approval).where(Approval.client_id == client.id, Approval.active.is_(True))).scalars():
        old.active = False
    snapshot = {c["key"]: c["ok"] for c in state["checks"]}
    a = Approval(client_id=client.id, run_id=run.id, decision="approved" if approve else "rejected",
                 comment=comment[:1000], approver_id=user.id, checklist=snapshot)
    db.add(a)
    db.flush()
    if approve:
        # The approver signs off the rules in force (part of the checklist), which confirms them for this client.
        complete_milestone(db, client.id, "rules_confirmed")
        complete_milestone(db, client.id, "go_live_approved")
    audit.record(db, user, "golive.approved" if approve else "golive.rejected", client_id=client.id,
                 entity="approval", entity_id=a.id,
                 detail={"run": run.id, "decision": run.decision, "rows_checked": run.rows_checked,
                         "blockers": run.blockers, "warnings": run.warnings, "checklist": snapshot,
                         "comment": comment[:1000]})
    return a
