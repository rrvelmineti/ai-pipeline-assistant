"""Submissions, validation runs and exception tracking.

Validation is deterministic: the same file, mapping and approved rules always give the same findings.
AI is never involved here, so an AI outage cannot weaken or skip a check.
"""
import csv
import hashlib
import time

from fastapi import HTTPException
from sqlalchemy import delete, func, insert, select

from claims_onboarding.readiness import readiness as readiness_facts
from claims_onboarding.rules import BLOCKER, parse_rules, validate
from orders_assistant.csv_check import MAX_FILE_BYTES, headers_of, reader

from . import audit
from .db import utcnow
from .models import (ExceptionEvent, ExceptionItem, Export, Finding, Mapping, RuleSet, Setting, Submission,
                     ValidationRun)
from .workflow import OPEN_STATES, complete_milestone, current_mapping, current_rule_set, latest_submission
FILE_GROUP = ("(file)", "file must be read completely", BLOCKER)


class SimulatedFailure(RuntimeError):
    pass


def read_headers(raw):
    try:
        return headers_of(reader(raw)), None
    except ValueError as exc:
        return [], str(exc)[:300]
    except (UnicodeError, csv.Error):
        return [], "The header could not be read: check UTF-8 encoding and CSV quoting."


def store_submission(db, store, client, user, filename, raw):
    """Save an upload. Sending the same bytes as the latest submission again is treated as an accidental
    duplicate and returns that submission (idempotent). Re-sending an older file after a newer one is a real
    resubmission and is accepted; the encrypted copy is shared because files are stored by content hash."""
    if not raw:
        raise HTTPException(422, "The file is empty.")
    if len(raw) > MAX_FILE_BYTES:
        raise HTTPException(413, "The upload exceeds the 20 MB limit; split the file.")
    sha = hashlib.sha256(raw).hexdigest()
    latest = latest_submission(db, client.id)
    if latest is not None and latest.sha256 == sha:
        audit.record(db, user, "submission.duplicate_ignored", client_id=client.id, entity="submission",
                     entity_id=latest.id, detail={"sha256": sha, "filename": filename})
        return latest, True
    _, key = store.put(client.id, raw)
    seq = (latest.sequence if latest else 0) + 1
    headers, error = read_headers(raw)
    sub = Submission(client_id=client.id, sequence=seq, filename=filename, sha256=sha, size_bytes=len(raw),
                     headers=headers, header_error=error, storage_key=key, uploaded_by=user.id)
    db.add(sub)
    db.flush()
    audit.record(db, user, "submission.uploaded", client_id=client.id, entity="submission", entity_id=sub.id,
                 detail={"sequence": seq, "filename": filename, "sha256": sha, "bytes": len(raw),
                         "columns": len(headers), "header_error": error})
    complete_milestone(db, client.id, "kickoff")
    return sub, False


def create_run(db, client, submission, user):
    rule_set = current_rule_set(db, client.id)
    mapping = current_mapping(db, client.id)
    if rule_set is None:
        raise HTTPException(409, "This client has no approved rule set.")
    if mapping is None:
        raise HTTPException(409, "Approve a column mapping for this client before validating.")
    specs = parse_rules(rule_set.text)
    unmapped = [f for f, s in specs.items() if s.required and not mapping.mapping.get(f)]
    if unmapped:
        raise HTTPException(409, "The approved mapping does not cover required fields in the current rules: "
                            + ", ".join(unmapped) + ". Create and approve a new mapping.")
    if not submission.header_error:
        absent = [c for c in mapping.mapping.values() if c and c not in submission.headers]
        if absent:
            raise HTTPException(409, "The approved mapping uses columns that are not in this file: "
                                + ", ".join(absent) + ". Create and approve a mapping for this file's layout.")
    run = ValidationRun(client_id=client.id, submission_id=submission.id, mapping_id=mapping.id,
                        rule_set_id=rule_set.id, status="queued", as_of=utcnow().date(), created_by=user.id)
    db.add(run)
    db.flush()
    audit.record(db, user, "run.queued", client_id=client.id, entity="run", entity_id=run.id,
                 detail={"submission": submission.sequence, "mapping_version": mapping.version,
                         "rule_set_version": rule_set.version})
    return run


def _take_fault(Session, key):
    """Consume a one-shot simulated fault in its own transaction, so a failed run cannot leave it armed."""
    with Session() as db:
        row = db.get(Setting, key)
        if row is None or not row.value.get("armed"):
            return False
        row.value = {"armed": False}
        db.commit()
        return True


def process_run(state, run_id):
    """Run one queued validation. Results are written in a single transaction, so an interruption leaves
    nothing half-saved: the run stays queued/running until recovery marks it interrupted for a retry."""
    Session = state.Session
    with Session() as db:
        run = db.get(ValidationRun, run_id)
        if run is None or run.status != "queued":
            return
        run.status, run.started_at, run.error = "running", utcnow(), None
        run.attempts += 1
        db.commit()
    started = time.perf_counter()
    if state.settings.simulation_enabled and _take_fault(Session, "hold_next_run"):
        return   # simulated crash: the run is left 'running' with nothing saved, as after a power cut
    try:
        if state.settings.simulation_enabled and _take_fault(Session, "fail_next_run"):
            raise SimulatedFailure("Simulated processing failure (fault injection).")
        with Session() as db:
            run = db.get(ValidationRun, run_id)
            sub = db.get(Submission, run.submission_id)
            rule_set = db.get(RuleSet, run.rule_set_id)
            mapping = db.get(Mapping, run.mapping_id)
            raw = state.store.get(sub.storage_key)
            specs = parse_rules(rule_set.text)
            report = validate(raw, mapping.mapping, specs, today=run.as_of)
            facts = readiness_facts(specs, mapping.mapping, report, mapping.corrections)
            db.execute(delete(Finding).where(Finding.run_id == run.id))
            if report.findings:
                db.execute(insert(Finding), [
                    {"run_id": run.id, "line": f["line"], "field": f["field"][:80],
                     "client_column": str(f["client_column"])[:200], "rule": f["rule"][:200],
                     "severity": f["severity"], "message": f["message"][:300],
                     "entered_enc": state.cipher.encrypt(f["entered"])} for f in report.findings])
            run.status, run.finished_at = "completed", utcnow()
            run.duration_ms = int((time.perf_counter() - started) * 1000)
            run.rows_checked, run.blockers, run.warnings = report.rows_checked, report.blockers, report.warnings
            run.scan_complete, run.decision = report.complete, facts["decision"]
            run.facts, run.findings_stored = facts, len(report.findings)
            summary = sync_exceptions(db, run, sub, facts)
            audit.record(db, None, "run.completed", client_id=run.client_id, entity="run", entity_id=run.id,
                         detail={"submission": sub.sequence, "decision": facts["decision"],
                                 "rows_checked": report.rows_checked, "blockers": report.blockers,
                                 "warnings": report.warnings, "scan_complete": report.complete,
                                 "exceptions": summary})
            complete_milestone(db, run.client_id, "first_validation")
            if report.complete and report.blockers == 0 and not _open_blockers(db, run.client_id):
                complete_milestone(db, run.client_id, "exceptions_cleared")
            db.commit()
    except Exception as exc:  # recorded on the run; the API reports it and offers a retry
        message = str(exc) if isinstance(exc, (SimulatedFailure, ValueError)) else f"{type(exc).__name__}: {exc}"
        with Session() as db:
            run = db.get(ValidationRun, run_id)
            run.status, run.finished_at, run.error = "failed", utcnow(), message[:500]
            run.duration_ms = int((time.perf_counter() - started) * 1000)
            audit.record(db, None, "run.failed", client_id=run.client_id, entity="run", entity_id=run.id,
                         detail={"error": run.error, "attempt": run.attempts})
            db.commit()


def _open_blockers(db, client_id):
    return db.execute(select(func.count(ExceptionItem.id)).where(
        ExceptionItem.client_id == client_id, ExceptionItem.severity == BLOCKER,
        ExceptionItem.status.in_(OPEN_STATES))).scalar()


def _event(db, exc, kind, actor=None, **detail):
    db.add(ExceptionEvent(exception_id=exc.id, kind=kind, actor_id=actor.id if actor else None, detail=detail))


def sync_exceptions(db, run, sub, facts):
    """Update the client's exception register from a completed run of its latest submission.

    Groups are matched by field, rule and severity, not by line, because resubmitted files reorder rows.
    Absent groups are resolved only when the whole file was read; an incomplete scan cannot clear anything.
    """
    latest = db.execute(select(func.max(Submission.sequence)).where(Submission.client_id == run.client_id)).scalar()
    if sub.sequence != latest:
        return {"skipped": "not the latest submission"}
    current = {(r["field"], r["rule"], r["severity"]): r["count"] for r in facts["findings_by_rule"]}
    if not facts["scan_complete"]:
        current[FILE_GROUP] = 1
    existing = {(e.field, e.rule, e.severity): e for e in
                db.execute(select(ExceptionItem).where(ExceptionItem.client_id == run.client_id)).scalars()}
    now, columns = utcnow(), facts.get("mapping", {})
    summary = {"created": 0, "reopened": 0, "resolved": 0, "still_open": 0}
    if facts["scan_complete"]:
        for key, e in existing.items():
            if key not in current and e.status != "resolved":
                _event(db, e, "auto_resolved", submission=sub.sequence, previous_status=e.status,
                       previous_count=e.current_count)
                e.status, e.resolved_at, e.updated_at = "resolved", now, now
                e.resolution = f"Not found in submission #{sub.sequence} (run {run.id})."
                e.current_count, e.last_run_id, e.last_submission = 0, run.id, sub.sequence
                summary["resolved"] += 1
    for key, count in current.items():
        e = existing.get(key)
        if e is None:
            field, rule, severity = key
            column = "(row)" if field == "(row)" else ("(file)" if field == "(file)" else columns.get(field) or "")
            e = ExceptionItem(client_id=run.client_id, field=field, client_column=column, rule=rule,
                              severity=severity, status="open", first_count=count, current_count=count,
                              first_run_id=run.id, last_run_id=run.id, first_submission=sub.sequence,
                              last_submission=sub.sequence, created_at=now, updated_at=now)
            db.add(e)
            db.flush()
            _event(db, e, "created", submission=sub.sequence, count=count)
            summary["created"] += 1
            continue
        if e.status == "resolved":
            _event(db, e, "reopened", submission=sub.sequence, count=count, reason="Found again after it was resolved.")
            e.status, e.resolved_at, e.resolution = "reopened", None, ""
            summary["reopened"] += 1
        elif e.status == "accepted" and count > e.current_count:
            _event(db, e, "reopened", submission=sub.sequence, count=count,
                   reason=f"Accepted at {e.current_count} rows; now {count} rows, so it needs review again.")
            e.status = "reopened"
            summary["reopened"] += 1
        elif e.last_submission != sub.sequence or e.current_count != count:
            _event(db, e, "still_open", submission=sub.sequence, before=e.current_count, after=count)
            summary["still_open"] += 1
        e.current_count, e.last_run_id, e.last_submission, e.updated_at = count, run.id, sub.sequence, now
    return summary


def retry_run(db, run, user):
    if run.status not in ("failed", "interrupted"):
        raise HTTPException(409, f"Only failed or interrupted runs can be retried; this run is {run.status}.")
    run.status, run.error = "queued", None
    audit.record(db, user, "run.retry", client_id=run.client_id, entity="run", entity_id=run.id,
                 detail={"previous_attempts": run.attempts})
    return run


def recover_interrupted(db):
    """Called at start-up: anything left mid-flight by a crash or restart is marked for a safe retry."""
    runs = db.execute(select(ValidationRun).where(ValidationRun.status.in_(("queued", "running")))).scalars().all()
    for run in runs:
        run.status = "interrupted"
        run.error = ("Processing stopped before it finished (the service restarted). Nothing from this attempt "
                     "was saved; retry to process the stored file again.")
        audit.record(db, None, "run.interrupted", client_id=run.client_id, entity="run", entity_id=run.id)
    exports = db.execute(select(Export).where(Export.status == "in_progress")).scalars().all()
    for exp in exports:
        exp.status = "failed"
        exp.last_error = ("The export stopped before it finished (the service restarted). Retry resumes from "
                          f"batch {exp.batches_done + 1}; batches already received are not loaded twice.")
        audit.record(db, None, "export.interrupted", client_id=exp.client_id, entity="export", entity_id=exp.id,
                     detail={"batches_done": exp.batches_done})
    return {"runs": len(runs), "exports": len(exports)}
