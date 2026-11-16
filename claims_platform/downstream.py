"""Export approved claims to a simulated downstream claims system.

Guarantees, each covered by a test:
- One export per approved validation run; asking again returns the same export.
- Batches carry a deterministic idempotency key. A replayed batch is acknowledged, not loaded twice.
- The downstream system holds each (client, claim_id) once, so overlapping resubmissions cannot duplicate claims.
- A failed or interrupted export resumes from the first unacknowledged batch.
"""
import hashlib
import json
import time

from fastapi import HTTPException
from sqlalchemy import insert, select

from orders_assistant.csv_check import headers_of, reader

from . import audit
from .db import utcnow
from .models import (Approval, Client, DownstreamBatch, DownstreamRecord, Export, Mapping, Setting, Submission,
                     ValidationRun)
from .workflow import client_state, complete_milestone

FAULT_KEY = "downstream_fault"


class DownstreamUnavailable(RuntimeError):
    pass


def batch_key(client_id, submission_sha, mapping_id, batch_size, index):
    return hashlib.sha256(f"{client_id}|{submission_sha}|{mapping_id}|{batch_size}|{index}".encode()).hexdigest()


def receive_batch(Session, cipher, client_id, export_id, key, records, fault=None):
    """The simulated downstream system's intake endpoint. Idempotent per batch key."""
    with Session() as db:
        seen_batch = db.execute(select(DownstreamBatch).where(DownstreamBatch.batch_key == key)).scalar_one_or_none()
        if seen_batch is not None:
            return {"accepted": seen_batch.accepted, "duplicates": seen_batch.duplicates, "replayed": True}
        if fault == "unavailable":
            raise DownstreamUnavailable("The downstream system did not respond (simulated outage).")
        ids = list({r["claim_id"] for r in records})
        already = set()
        for i in range(0, len(ids), 500):
            already |= set(db.execute(select(DownstreamRecord.claim_id).where(
                DownstreamRecord.client_id == client_id, DownstreamRecord.claim_id.in_(ids[i:i + 500]))).scalars())
        rows, taken, duplicates, now = [], set(), 0, utcnow()
        for r in records:
            cid = r["claim_id"]
            if cid in already or cid in taken:
                duplicates += 1
                continue
            taken.add(cid)
            rows.append({"client_id": client_id, "claim_id": cid, "batch_key": key, "received_at": now,
                         "payload_enc": cipher.encrypt(json.dumps(r, sort_keys=True))})
        if rows:
            db.execute(insert(DownstreamRecord), rows)
        db.add(DownstreamBatch(batch_key=key, client_id=client_id, export_id=export_id, accepted=len(rows),
                               duplicates=duplicates, received_at=now))
        db.commit()
    if fault == "lost_ack":
        raise DownstreamUnavailable("The connection dropped before the acknowledgement arrived (simulated).")
    return {"accepted": len(rows), "duplicates": duplicates, "replayed": False}


def _next_fault(Session, index):
    """Read and consume the configured simulated fault for this batch, in its own transaction."""
    with Session() as db:
        row = db.get(Setting, FAULT_KEY)
        if row is None or not row.value:
            return None
        cfg = dict(row.value)
        mode = cfg.get("mode")
        fault = None
        if mode == "outage" and cfg.get("remaining", 0) > 0 and index >= cfg.get("from_batch", 0):
            cfg["remaining"] -= 1
            fault = "unavailable"
        elif mode in ("transient", "lost_ack") and index in cfg.get("batches", []) and index not in cfg.get("fired", []):
            cfg["fired"] = cfg.get("fired", []) + [index]
            fault = "unavailable" if mode == "transient" else "lost_ack"
        row.value = cfg
        db.commit()
        return fault


def mapped_records(raw, mapping):
    rows = reader(raw)
    headers = headers_of(rows)
    pos = {h: i for i, h in enumerate(headers)}
    cols = {f: pos[c] for f, c in mapping.items() if c}
    for row in rows:
        yield {f: row[i].strip() for f, i in cols.items()}


def start_export(db, client, user, batch_size):
    state = client_state(db, client)
    run, approval = state["run"], state["approval"]
    if run is not None:
        existing = db.execute(select(Export).where(Export.run_id == run.id)).scalar_one_or_none()
        if existing is not None:
            return existing, True
    if run is None or approval is None or approval.decision != "approved":
        raise HTTPException(409, "Export needs a go-live approval for the latest validated file.")
    if not state["ready_for_approval"]:
        raise HTTPException(409, "The client is no longer ready (something changed after approval). Re-validate first.")
    exp = Export(client_id=client.id, run_id=run.id, approval_id=approval.id, status="pending",
                 batch_size=batch_size, created_by=user.id)
    db.add(exp)
    db.flush()
    audit.record(db, user, "export.requested", client_id=client.id, entity="export", entity_id=exp.id,
                 detail={"run": run.id, "approval": approval.id, "batch_size": batch_size})
    return exp, False


def retry_export(db, exp, user):
    if exp.status != "failed":
        raise HTTPException(409, f"Only failed exports can be retried; this export is {exp.status}.")
    exp.status = "pending"
    audit.record(db, user, "export.retry", client_id=exp.client_id, entity="export", entity_id=exp.id,
                 detail={"resume_from_batch": exp.batches_done + 1})
    return exp


def run_export(state, export_id):
    Session, settings = state.Session, state.settings
    with Session() as db:
        exp = db.get(Export, export_id)
        if exp is None or exp.status != "pending":
            return
        exp.status, exp.attempts, exp.last_error = "in_progress", exp.attempts + 1, None
        run = db.get(ValidationRun, exp.run_id)
        sub, mapping = db.get(Submission, run.submission_id), db.get(Mapping, run.mapping_id)
        client_id, sha, mapping_id, cols, size = exp.client_id, sub.sha256, mapping.id, dict(mapping.mapping), exp.batch_size
        storage_key, start_batch = sub.storage_key, exp.batches_done
        db.commit()
    started = time.perf_counter()
    try:
        records = list(mapped_records(state.store.get(storage_key), cols))
        batches = [records[i:i + size] for i in range(0, len(records), size)]
        with Session() as db:
            exp = db.get(Export, export_id)
            exp.total_records, exp.batches_total = len(records), len(batches)
            db.commit()
        for index in range(start_batch, len(batches)):
            key = batch_key(client_id, sha, mapping_id, size, index)
            ack, last_error, retries = None, None, 0
            for attempt in range(settings.export_batch_attempts):
                fault = _next_fault(Session, index) if settings.simulation_enabled else None
                try:
                    ack = receive_batch(Session, state.cipher, client_id, export_id, key, batches[index], fault)
                    break
                except DownstreamUnavailable as exc:
                    last_error = str(exc)
                    if attempt + 1 < settings.export_batch_attempts:
                        retries += 1
            with Session() as db:
                exp = db.get(Export, export_id)
                exp.batch_retries += retries
                if ack is None:
                    exp.status, exp.last_error = "failed", (f"Batch {index + 1} of {len(batches)} failed after "
                                                            f"{settings.export_batch_attempts} attempts: {last_error}")
                    exp.duration_ms = int((time.perf_counter() - started) * 1000)
                    audit.record(db, None, "export.failed", client_id=client_id, entity="export", entity_id=export_id,
                                 detail={"batch": index + 1, "batches_done": exp.batches_done, "error": last_error})
                    db.commit()
                    return
                exp.batches_done = index + 1
                exp.sent_records += ack["accepted"]
                exp.skipped_duplicates += ack["duplicates"]
                db.commit()
        with Session() as db:
            exp = db.get(Export, export_id)
            exp.status, exp.finished_at = "completed", utcnow()
            exp.duration_ms = int((time.perf_counter() - started) * 1000)
            db.get(Client, client_id).status = "live"
            complete_milestone(db, client_id, "production_export")
            audit.record(db, None, "export.completed", client_id=client_id, entity="export", entity_id=export_id,
                         detail={"records": exp.total_records, "loaded": exp.sent_records,
                                 "skipped_duplicates": exp.skipped_duplicates, "batches": exp.batches_total,
                                 "batch_retries": exp.batch_retries, "attempts": exp.attempts})
            db.commit()
    except Exception as exc:
        with Session() as db:
            exp = db.get(Export, export_id)
            exp.status, exp.last_error = "failed", f"{type(exc).__name__}: {exc}"[:500]
            audit.record(db, None, "export.failed", client_id=client_id, entity="export", entity_id=export_id,
                         detail={"error": exp.last_error})
            db.commit()


def set_fault(db, user, config):
    row = db.get(Setting, FAULT_KEY)
    value = dict(config or {})
    if row is None:
        db.add(Setting(key=FAULT_KEY, value=value))
    else:
        row.value = value
    audit.record(db, user, "simulation.downstream_fault", detail=value)


def approval_for(db, exp):
    return db.get(Approval, exp.approval_id)
