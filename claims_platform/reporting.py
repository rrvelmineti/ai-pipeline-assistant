"""Scorecards, KPIs, processing metrics, resubmission history and the go-live evidence package.

Every figure is computed from records in the database. Nothing is estimated, and no improvement over a
manual baseline is claimed until a baseline has actually been measured (see docs/platform/business-case.md).
"""
import csv
import hashlib
import io
import json
import statistics
import zipfile

from fastapi import HTTPException
from sqlalchemy import select

from claims_onboarding.handoff import compare_submissions
from claims_onboarding.readiness import markdown_report, written_summary

from . import __version__, audit
from .db import utcnow
from .models import (Approval, AuditEntry, Client, ExceptionEvent, ExceptionItem, Export, Finding, Mapping,
                     Milestone, RuleSet, Submission, User, ValidationRun)
from .workflow import client_state, latest_run

BASELINE_NOTE = ("No manual baseline has been measured for this pilot, so no time or effort saving is claimed. "
                 "See docs/platform/business-case.md for how to measure one.")


def _hours(a, b):
    return round((b - a).total_seconds() / 3600, 2)


def _median(values):
    return round(statistics.median(values), 2) if values else None


def _p95(values):
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))]


def run_summary(run):
    if run is None:
        return None
    return {"id": run.id, "status": run.status, "attempts": run.attempts, "error": run.error,
            "rows_checked": run.rows_checked, "blockers": run.blockers, "warnings": run.warnings,
            "scan_complete": run.scan_complete, "decision": run.decision, "duration_ms": run.duration_ms,
            "mapping_id": run.mapping_id, "rule_set_id": run.rule_set_id,
            "queued_at": run.queued_at, "finished_at": run.finished_at}


def resubmission_history(db, client):
    """Each submission with its result, and what changed against the previous submission."""
    subs = db.execute(select(Submission).where(Submission.client_id == client.id)
                      .order_by(Submission.sequence)).scalars().all()
    out, previous = [], None
    for s in subs:
        run = latest_run(db, s.id, completed_only=True)
        item = {"submission_id": s.id, "sequence": s.sequence, "filename": s.filename, "uploaded_at": s.uploaded_at,
                "sha256": s.sha256, "run": run_summary(run or latest_run(db, s.id)), "comparison": None}
        if run is not None and run.facts:
            if previous is not None:
                c = compare_submissions(previous, run.facts)
                item["comparison"] = {
                    "fixed": [r for r in c["rows"] if r["status"] == "fixed"],
                    "new": [r for r in c["rows"] if r["status"] == "new"],
                    "unresolved": [r for r in c["rows"] if r["status"] in ("unchanged", "improved", "worse")],
                    "mapping_changed": c["mapping_changed"], "same_file": c["same_file"],
                    "previous_blockers": c["previous_blockers"], "current_blockers": c["current_blockers"]}
            previous = run.facts
        out.append(item)
    return out


def scorecard(db, client):
    history = resubmission_history(db, client)
    validated = [h for h in history if h["run"] and h["run"]["status"] == "completed"]
    first_ready = next((h["sequence"] for h in validated if h["run"]["decision"] == "Ready"), None)
    exceptions = db.execute(select(ExceptionItem).where(ExceptionItem.client_id == client.id)).scalars().all()
    resolved = [e for e in exceptions if e.status == "resolved" and e.resolved_at]
    milestones = db.execute(select(Milestone).where(Milestone.client_id == client.id)).scalars().all()
    ended = client.status == "live" and db.execute(
        select(Export.finished_at).where(Export.client_id == client.id, Export.status == "completed")
        .order_by(Export.finished_at)).scalars().first()
    return {
        "client": {"id": client.id, "code": client.code, "name": client.name, "status": client.status},
        "submissions": len(history),
        "validated_submissions": len(validated),
        "rounds_to_acceptance": first_ready,
        "first_pass_acceptance": (validated[0]["run"]["decision"] == "Ready") if validated else None,
        "rework_rate": round(sum(h["run"]["decision"] != "Ready" for h in validated) / len(validated), 3) if validated else None,
        "blockers_by_submission": [{"sequence": h["sequence"], "blockers": h["run"]["blockers"],
                                    "warnings": h["run"]["warnings"], "decision": h["run"]["decision"]} for h in validated],
        "exceptions": {
            "total": len(exceptions),
            "open": sum(e.status in ("open", "in_progress", "reopened") for e in exceptions),
            "resolved": len(resolved), "accepted": sum(e.status == "accepted" for e in exceptions),
            "reopened_ever": len({ev.exception_id for ev in db.execute(select(ExceptionEvent).where(
                ExceptionEvent.kind == "reopened",
                ExceptionEvent.exception_id.in_([e.id for e in exceptions] or [-1]))).scalars()}),
            "median_hours_to_resolve": _median([_hours(e.created_at, e.resolved_at) for e in resolved]),
        },
        "days_in_onboarding": ((ended or utcnow()) - client.created_at).days,
        "milestones_done": sum(m.status == "done" for m in milestones), "milestones_total": len(milestones),
    }


def portfolio(db, client_ids):
    """KPIs across the clients this user can see, each with its sample size and definition."""
    clients = db.execute(select(Client).where(Client.id.in_(client_ids or [-1])).order_by(Client.code)).scalars().all()
    cards = [scorecard(db, c) for c in clients]
    with_runs = [c for c in cards if c["validated_submissions"]]
    accepted = [c for c in cards if c["rounds_to_acceptance"]]
    validated_total = sum(c["validated_submissions"] for c in cards)
    not_ready = sum(sum(b["decision"] != "Ready" for b in c["blockers_by_submission"]) for c in cards)
    metrics = processing_metrics(db, client_ids)
    resolved_hours = []
    for cid in client_ids or []:
        for e in db.execute(select(ExceptionItem).where(ExceptionItem.client_id == cid,
                                                        ExceptionItem.status == "resolved")).scalars():
            if e.resolved_at:
                resolved_hours.append(_hours(e.created_at, e.resolved_at))

    def kpi(name, value, n, definition):
        return {"name": name, "value": value, "n": n, "definition": definition}
    return {
        "clients": len(cards), "live": sum(c["client"]["status"] == "live" for c in cards),
        "kpis": [
            kpi("First-pass acceptance rate",
                round(sum(c["first_pass_acceptance"] for c in with_runs) / len(with_runs), 3) if with_runs else None,
                len(with_runs), "Clients whose first validated file was Ready ÷ clients with a validated file."),
            kpi("Mean rounds to acceptance",
                round(sum(c["rounds_to_acceptance"] for c in accepted) / len(accepted), 2) if accepted else None,
                len(accepted), "Submissions up to and including the first Ready file, for clients that reached Ready."),
            kpi("Rework rate", round(not_ready / validated_total, 3) if validated_total else None, validated_total,
                "Validated submissions that were Not ready ÷ all validated submissions."),
            kpi("Median hours to resolve an exception", _median(resolved_hours), len(resolved_hours),
                "From the run that opened an exception group to the run that no longer contained it."),
            kpi("Validation runs completed on first attempt", metrics["runs"]["first_attempt_success_rate"],
                metrics["runs"]["finished"], "Completed runs with one attempt ÷ runs that finished (completed or failed)."),
            kpi("Exports completed", metrics["exports"]["completion_rate"], metrics["exports"]["total"],
                "Completed exports ÷ exports requested."),
        ],
        "validation_accuracy": "Measured offline against planted errors: python -m evaluation.platform_scenarios "
                               "(results in evaluation/results/platform_scenarios.json).",
        "baseline": BASELINE_NOTE,
        "scorecards": cards,
    }


def processing_metrics(db, client_ids):
    ids = client_ids or [-1]
    runs = db.execute(select(ValidationRun).where(ValidationRun.client_id.in_(ids))).scalars().all()
    exports = db.execute(select(Export).where(Export.client_id.in_(ids))).scalars().all()
    by_status = {}
    for r in runs:
        by_status[r.status] = by_status.get(r.status, 0) + 1
    done = [r for r in runs if r.status == "completed" and r.duration_ms is not None]
    finished = [r for r in runs if r.status in ("completed", "failed")]
    durations = [r.duration_ms for r in done]
    total_ms = sum(durations)
    codes = dict(db.execute(select(Client.id, Client.code).where(Client.id.in_(ids))).all())
    recent = sorted(runs, key=lambda r: r.id, reverse=True)[:20]
    return {
        "runs": {
            "total": len(runs), "by_status": by_status, "finished": len(finished),
            "retried": sum(r.attempts > 1 for r in runs),
            "first_attempt_success_rate": round(sum(r.status == "completed" and r.attempts == 1 for r in finished)
                                                / len(finished), 3) if finished else None,
            "median_ms": _median(durations), "p95_ms": _p95(durations), "max_ms": max(durations) if durations else None,
            "rows_validated": sum(r.rows_checked or 0 for r in done),
            "rows_per_second": round(sum(r.rows_checked or 0 for r in done) / (total_ms / 1000)) if total_ms else None,
            "largest_file_rows": max((r.rows_checked or 0 for r in done), default=None),
        },
        "exports": {
            "total": len(exports), "completed": sum(e.status == "completed" for e in exports),
            "failed": sum(e.status == "failed" for e in exports),
            "completion_rate": round(sum(e.status == "completed" for e in exports) / len(exports), 3) if exports else None,
            "records_loaded": sum(e.sent_records for e in exports),
            "duplicates_skipped": sum(e.skipped_duplicates for e in exports),
            "batch_retries": sum(e.batch_retries for e in exports),
        },
        "recent_runs": [{"id": r.id, "client": codes.get(r.client_id), "status": r.status, "attempts": r.attempts,
                         "rows_checked": r.rows_checked, "duration_ms": r.duration_ms, "decision": r.decision,
                         "queued_at": r.queued_at} for r in recent],
    }


def findings_rows(db, cipher, run_id):
    for f in db.execute(select(Finding).where(Finding.run_id == run_id).order_by(Finding.line, Finding.id)).scalars():
        yield {"line": f.line, "field": f.field, "client_column": f.client_column,
               "entered": cipher.decrypt_text(f.entered_enc), "rule": f.rule, "severity": f.severity,
               "message": f.message}


def findings_csv_text(rows):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=["line", "field", "client_column", "entered", "rule", "severity", "message"],
                       lineterminator="\n")
    w.writeheader()
    for r in rows:
        # Neutralise spreadsheet formulas in values sent by the client.
        r = dict(r, entered=("'" + r["entered"]) if r["entered"][:1] in ("=", "+", "-", "@") else r["entered"])
        w.writerow(r)
    return buf.getvalue()


def _json(obj):
    return json.dumps(obj, indent=2, default=str, sort_keys=True) + "\n"


def evidence_package(db, cipher, client, user):
    """A ZIP of everything an auditor needs for the go-live decision, with a SHA-256 manifest."""
    state = client_state(db, client)
    run = state["run"]
    if run is None:
        raise HTTPException(409, "There is no completed validation to package.")
    names = dict(db.execute(select(User.id, User.username)).all())
    rs, mp, sub = db.get(RuleSet, run.rule_set_id), db.get(Mapping, run.mapping_id), db.get(Submission, run.submission_id)
    facts = run.facts
    exceptions = db.execute(select(ExceptionItem).where(ExceptionItem.client_id == client.id)
                            .order_by(ExceptionItem.id)).scalars().all()
    events = db.execute(select(ExceptionEvent).where(ExceptionEvent.exception_id.in_([e.id for e in exceptions] or [-1]))
                        .order_by(ExceptionEvent.id)).scalars().all()
    exc_buf = io.StringIO()
    w = csv.writer(exc_buf, lineterminator="\n")
    w.writerow(["id", "field", "client_column", "rule", "severity", "status", "owner", "first_count", "current_count",
                "first_submission", "last_submission", "resolution", "created_at", "resolved_at"])
    for e in exceptions:
        w.writerow([e.id, e.field, e.client_column, e.rule, e.severity, e.status, names.get(e.owner_id, ""),
                    e.first_count, e.current_count, e.first_submission, e.last_submission, e.resolution,
                    e.created_at, e.resolved_at or ""])
    approvals = db.execute(select(Approval).where(Approval.client_id == client.id).order_by(Approval.id)).scalars().all()
    exports = db.execute(select(Export).where(Export.client_id == client.id).order_by(Export.id)).scalars().all()
    trail = db.execute(select(AuditEntry).where(AuditEntry.client_id == client.id).order_by(AuditEntry.id)).scalars().all()
    files = {
        "README.txt": (f"Go-live evidence package for {client.name} ({client.code}).\n"
                       f"Generated {utcnow().isoformat(timespec='seconds')}Z by {user.username} with platform v{__version__}.\n\n"
                       "Synthetic data only. This pilot is not HIPAA-compliant and is not for real patient records.\n"
                       "manifest.json lists the SHA-256 of every file; recompute them to confirm nothing changed.\n"),
        "readiness_report.md": markdown_report(facts, written_summary(facts)),
        "readiness_facts.json": _json(facts),
        "readiness_checklist.json": _json({"stage": state["stage"], "ready_for_approval": state["ready_for_approval"],
                                           "checks": state["checks"]}),
        "findings.csv": findings_csv_text(findings_rows(db, cipher, run.id)),
        f"rules_v{rs.version}.txt": rs.text,
        "rule_set.json": _json({"version": rs.version, "status": rs.status, "note": rs.note,
                                "author": names.get(rs.author_id, "system"), "approver": names.get(rs.approver_id, "system"),
                                "approved_at": rs.approved_at}),
        "mapping.json": _json({"version": mp.version, "status": mp.status, "headers": mp.headers, "mapping": mp.mapping,
                               "suggestions": mp.suggestions, "confirmed_fields": mp.confirmed_fields,
                               "corrections": mp.corrections, "author": names.get(mp.author_id),
                               "approver": names.get(mp.approver_id), "approved_at": mp.approved_at,
                               "review_comment": mp.review_comment}),
        "exceptions.csv": exc_buf.getvalue(),
        "exception_history.json": _json([{"exception_id": ev.exception_id, "at": ev.at, "kind": ev.kind,
                                          "actor": names.get(ev.actor_id, "system"), "detail": ev.detail} for ev in events]),
        "resubmissions.json": _json(resubmission_history(db, client)),
        "approvals.json": _json([{"id": a.id, "run_id": a.run_id, "decision": a.decision, "approver": names.get(a.approver_id),
                                  "comment": a.comment, "checklist": a.checklist, "at": a.at, "active": a.active}
                                 for a in approvals]),
        "exports.json": _json([{"id": x.id, "run_id": x.run_id, "status": x.status, "total_records": x.total_records,
                                "loaded": x.sent_records, "skipped_duplicates": x.skipped_duplicates,
                                "batches": x.batches_total, "batch_retries": x.batch_retries, "attempts": x.attempts,
                                "finished_at": x.finished_at} for x in exports]),
        "audit_trail.json": _json({"chain_check": audit.verify(db),
                                   "entries": [{"id": a.id, "at": a.at, "actor": a.actor, "action": a.action,
                                                "entity": a.entity, "entity_id": a.entity_id, "detail": a.detail,
                                                "hash": a.hash} for a in trail]}),
    }
    manifest = {"client": client.code, "run_id": run.id, "submission": sub.sequence, "file_sha256": sub.sha256,
                "decision": run.decision, "stage": state["stage"], "generated_by": user.username,
                "generated_at": utcnow().isoformat(timespec="seconds") + "Z",
                "files": {name: hashlib.sha256(body.encode()).hexdigest() for name, body in sorted(files.items())}}
    files["manifest.json"] = _json(manifest)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, body in sorted(files.items()):
            z.writestr(f"{client.code}-evidence/{name}", body)
    digest = hashlib.sha256(files["manifest.json"].encode()).hexdigest()
    audit.record(db, user, "evidence.generated", client_id=client.id, entity="run", entity_id=run.id,
                 detail={"manifest_sha256": digest, "files": len(files)})
    return buf.getvalue(), digest
