"""Append-only audit trail. Each entry's hash covers the previous hash, so edits or deletions are detectable."""
import hashlib
import json

from sqlalchemy import select

from .db import utcnow
from .models import AuditEntry, AuditHead

GENESIS = "0" * 64


def _digest(prev_hash, at, actor, action, client_id, entity, entity_id, detail):
    body = json.dumps([prev_hash, at.isoformat(timespec="microseconds"), actor, action, client_id, entity,
                       entity_id, detail], sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(body.encode()).hexdigest()


def record(db, actor, action, *, client_id=None, entity="", entity_id=None, detail=None):
    """Add an audit entry in the caller's transaction. actor is a User or None for the system."""
    head = db.execute(select(AuditHead).where(AuditHead.id == 1).with_for_update()).scalar_one_or_none()
    if head is None:
        head = AuditHead(id=1, last_hash=GENESIS, entries=0)
        db.add(head)
        db.flush()
    detail = json.loads(json.dumps(detail or {}, default=str))
    at = utcnow()
    name = actor.username if actor is not None else "system"
    actor_id = actor.id if actor is not None else None
    digest = _digest(head.last_hash, at, name, action, client_id, entity, entity_id, detail)
    entry = AuditEntry(at=at, actor_id=actor_id, actor=name, action=action, client_id=client_id, entity=entity,
                       entity_id=entity_id, detail=detail, prev_hash=head.last_hash, hash=digest)
    db.add(entry)
    head.last_hash = digest
    head.entries += 1
    return entry


def verify(db):
    """Recompute the whole chain. Returns {ok, entries, first_bad_id}."""
    prev, count = GENESIS, 0
    for e in db.execute(select(AuditEntry).order_by(AuditEntry.id)).scalars():
        count += 1
        if e.prev_hash != prev or _digest(prev, e.at, e.actor, e.action, e.client_id, e.entity, e.entity_id,
                                          e.detail) != e.hash:
            return {"ok": False, "entries": count, "first_bad_id": e.id}
        prev = e.hash
    head = db.get(AuditHead, 1)
    if head is not None and (head.last_hash != prev or head.entries != count):
        return {"ok": False, "entries": count, "first_bad_id": None, "detail": "Entries were removed from the end."}
    return {"ok": True, "entries": count, "first_bad_id": None}
