"""HTTP API. Every route checks the signed-in user's role and, for client data, their access to that client."""
import hashlib
import os
import re
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from claims_onboarding.rules import BLOCKER, RULES_PATH, parse_rules
from orders_assistant.csv_check import MAX_FILE_BYTES
from orders_assistant.explain import ExplanationError

from . import __version__, audit, comms, downstream, processing, reporting, workflow
from .db import utcnow
from .deps import (accessible_client_ids, can_access, client_or_404, current_user, get_db, owned_or_404,
                   require_role)
from .mapping_service import ai_error_text, check_mapping, suggest
from .models import (ROLES, Approval, AuditEntry, AuthSession, Client, ClientAccess, Communication, DownstreamBatch,
                     DownstreamRecord, ExceptionEvent, ExceptionItem, Export, Finding, Mapping, MappingTemplate,
                     Milestone, RuleSet, Setting, Submission, User, ValidationRun)
from .security import (burn_password_check, check_password_strength, hash_password, new_token, verify_password)

ANALYSTS = ("admin", "implementation_analyst")
APPROVERS = ("admin", "approver")
INTERNAL = ("admin", "implementation_analyst", "approver")

router = APIRouter(prefix="/api")


# --- request bodies ----------------------------------------------------------------------------------

class LoginIn(BaseModel):
    username: str = Field(max_length=80)
    password: str = Field(max_length=200)


class PasswordIn(BaseModel):
    current_password: str = Field(max_length=200)
    new_password: str = Field(max_length=200)


class UserIn(BaseModel):
    username: str = Field(pattern=r"^[a-z0-9._-]{3,40}$")
    display_name: str = Field(min_length=1, max_length=120)
    role: str
    password: str = Field(max_length=200)


class UserPatch(BaseModel):
    active: Optional[bool] = None
    role: Optional[str] = None
    unlock: bool = False


class ClientIn(BaseModel):
    code: str = Field(pattern=r"^[A-Z0-9-]{2,40}$")
    name: str = Field(min_length=2, max_length=160)
    go_live_target: Optional[date] = None


class ClientPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=160)
    go_live_target: Optional[date] = None
    status: Optional[str] = None


class AccessIn(BaseModel):
    user_id: int


class RuleSetIn(BaseModel):
    text: str = Field(max_length=50_000)
    note: str = Field(default="", max_length=500)


class ReviewIn(BaseModel):
    approve: bool
    comment: str = Field(default="", max_length=1000)


class SuggestIn(BaseModel):
    use_ai: bool = False


class MappingPut(BaseModel):
    mapping: dict[str, Optional[str]]
    confirmed_fields: list[str] = []
    note: str = Field(default="", max_length=500)
    submit: bool = False


class TemplateIn(BaseModel):
    name: str = Field(min_length=3, max_length=120)


class ExceptionPatch(BaseModel):
    owner_id: Optional[int] = None
    clear_owner: bool = False
    status: Optional[str] = None
    note: str = Field(default="", max_length=1000)


class CommIn(BaseModel):
    kind: str
    subject: str = Field(default="", max_length=200)
    body: str = Field(default="", max_length=20_000)


class MilestonePatch(BaseModel):
    status: Optional[str] = None
    due_date: Optional[date] = None


class SimulationIn(BaseModel):
    downstream_fault: Optional[dict] = None
    fail_next_run: bool = False
    hold_next_run: bool = False


# --- output helpers ----------------------------------------------------------------------------------

def user_out(u):
    return {"id": u.id, "username": u.username, "display_name": u.display_name, "role": u.role, "active": u.active,
            "locked": bool(u.locked_until and u.locked_until > utcnow())}


def names(db):
    return dict(db.execute(select(User.id, User.display_name)).all())


def client_out(c):
    return {"id": c.id, "code": c.code, "name": c.name, "status": c.status, "go_live_target": c.go_live_target,
            "created_at": c.created_at}


def state_out(state):
    a, x = state["approval"], state["export"]
    return {**{k: v for k, v in state.items() if k not in ("run", "approval", "export")},
            "run": reporting.run_summary(state["run"]),
            "approval": {"id": a.id, "decision": a.decision, "comment": a.comment, "approver_id": a.approver_id,
                         "at": a.at} if a else None,
            "export": export_out(x) if x else None}


def export_out(x):
    return {"id": x.id, "run_id": x.run_id, "status": x.status, "total_records": x.total_records,
            "batches_total": x.batches_total, "batches_done": x.batches_done, "sent_records": x.sent_records,
            "skipped_duplicates": x.skipped_duplicates, "batch_retries": x.batch_retries, "attempts": x.attempts,
            "last_error": x.last_error, "created_at": x.created_at, "finished_at": x.finished_at,
            "duration_ms": x.duration_ms}


def submission_out(s):
    return {"id": s.id, "sequence": s.sequence, "filename": s.filename, "sha256": s.sha256, "size_bytes": s.size_bytes,
            "headers": s.headers, "header_error": s.header_error, "uploaded_at": s.uploaded_at}


def mapping_out(m, who):
    return {"id": m.id, "version": m.version, "status": m.status, "submission_id": m.submission_id,
            "headers": m.headers, "suggestions": m.suggestions, "mapping": m.mapping,
            "confirmed_fields": m.confirmed_fields, "corrections": m.corrections, "note": m.note,
            "author": who.get(m.author_id), "author_id": m.author_id, "approver": who.get(m.approver_id),
            "review_comment": m.review_comment, "created_at": m.created_at, "approved_at": m.approved_at}


def ruleset_out(r, who):
    return {"id": r.id, "version": r.version, "status": r.status, "note": r.note, "text": r.text,
            "author": who.get(r.author_id, "system"), "author_id": r.author_id,
            "approver": who.get(r.approver_id, "system" if r.status == "approved" and r.version == 1 else None),
            "created_at": r.created_at, "approved_at": r.approved_at}


def exception_out(e, who):
    return {"id": e.id, "field": e.field, "client_column": e.client_column, "rule": e.rule, "severity": e.severity,
            "status": e.status, "owner_id": e.owner_id, "owner": who.get(e.owner_id), "resolution": e.resolution,
            "first_count": e.first_count, "current_count": e.current_count, "first_submission": e.first_submission,
            "last_submission": e.last_submission, "created_at": e.created_at, "updated_at": e.updated_at,
            "resolved_at": e.resolved_at}


def comm_out(c, who, cipher=None):
    out = {"id": c.id, "kind": c.kind, "subject": c.subject, "status": c.status, "run_id": c.run_id,
           "created_by": who.get(c.created_by), "created_at": c.created_at, "sent_by": who.get(c.sent_by),
           "sent_at": c.sent_at}
    if cipher is not None:
        out["body"] = cipher.decrypt_text(c.body_enc)
    return out


def state_of(request):
    return request.app.state


# --- auth --------------------------------------------------------------------------------------------

@router.get("/health")
def health(db=Depends(get_db)):
    db.execute(select(1))
    return {"status": "ok", "version": __version__}


@router.post("/auth/login")
def login(body: LoginIn, request: Request, db=Depends(get_db)):
    settings = state_of(request).settings
    user = db.execute(select(User).where(User.username == body.username.strip().lower())).scalar_one_or_none()
    now = utcnow()
    wrong = HTTPException(401, "Incorrect username or password.")
    if user is None or not user.active:
        burn_password_check(body.password)
        audit.record(db, None, "login.failed", detail={"username": body.username.strip().lower()[:80]})
        db.commit()
        raise wrong
    if user.locked_until and user.locked_until > now:
        audit.record(db, user, "login.blocked_locked")
        db.commit()
        raise HTTPException(423, "Too many failed sign-ins. Try again later or ask an administrator to unlock the account.")
    if not verify_password(body.password, user.password_hash):
        user.failed_logins += 1
        audit.record(db, user, "login.failed", detail={"consecutive_failures": user.failed_logins})
        if user.failed_logins >= settings.lockout_attempts:
            user.locked_until, user.failed_logins = now + timedelta(minutes=settings.lockout_minutes), 0
            audit.record(db, user, "user.locked", detail={"minutes": settings.lockout_minutes})
        db.commit()
        raise wrong
    user.failed_logins, user.locked_until = 0, None
    token, digest = new_token()
    expires = now + timedelta(hours=settings.session_hours)
    db.add(AuthSession(token_hash=digest, user_id=user.id, expires_at=expires))
    audit.record(db, user, "login.succeeded")
    db.commit()
    return {"token": token, "expires_at": expires, "user": user_out(user)}


@router.post("/auth/logout")
def logout(request: Request, user=Depends(current_user), db=Depends(get_db)):
    session = db.get(AuthSession, request.state.auth_session.id)
    session.revoked = True
    audit.record(db, user, "logout")
    db.commit()
    return {"ok": True}


@router.get("/auth/me")
def me(user=Depends(current_user), db=Depends(get_db)):
    return {"user": user_out(user), "client_ids": accessible_client_ids(db, user)}


@router.post("/auth/password")
def change_password(body: PasswordIn, user=Depends(current_user), db=Depends(get_db)):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(403, "The current password is wrong.")
    try:
        check_password_strength(body.new_password)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    user.password_hash = hash_password(body.new_password)
    for s in db.execute(select(AuthSession).where(AuthSession.user_id == user.id)).scalars():
        s.revoked = True
    audit.record(db, user, "user.password_changed", entity="user", entity_id=user.id)
    db.commit()
    return {"ok": True, "detail": "Password changed. Sign in again."}


# --- users and access (admin) ------------------------------------------------------------------------

@router.get("/users")
def list_users(user=Depends(current_user), db=Depends(get_db)):
    require_role(user, "admin")
    return [user_out(u) for u in db.execute(select(User).order_by(User.username)).scalars()]


@router.post("/users", status_code=201)
def create_user(body: UserIn, user=Depends(current_user), db=Depends(get_db)):
    require_role(user, "admin")
    if body.role not in ROLES:
        raise HTTPException(422, "role must be one of " + ", ".join(ROLES) + ".")
    try:
        check_password_strength(body.password)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    if db.execute(select(User.id).where(User.username == body.username)).first():
        raise HTTPException(409, "That username is taken.")
    u = User(username=body.username, display_name=body.display_name, role=body.role,
             password_hash=hash_password(body.password))
    db.add(u)
    db.flush()
    audit.record(db, user, "user.created", entity="user", entity_id=u.id,
                 detail={"username": u.username, "role": u.role})
    db.commit()
    return user_out(u)


@router.patch("/users/{user_id}")
def patch_user(user_id: int, body: UserPatch, user=Depends(current_user), db=Depends(get_db)):
    require_role(user, "admin")
    u = db.get(User, user_id)
    if u is None:
        raise HTTPException(404, "Not found.")
    changes = {}
    if body.role is not None:
        if body.role not in ROLES:
            raise HTTPException(422, "Unknown role.")
        if u.id == user.id and body.role != "admin":
            raise HTTPException(409, "You cannot remove your own administrator role.")
        changes["role"], u.role = [u.role, body.role], body.role
    if body.active is not None:
        if u.id == user.id and not body.active:
            raise HTTPException(409, "You cannot disable your own account.")
        changes["active"], u.active = [u.active, body.active], body.active
        if not body.active:
            for s in db.execute(select(AuthSession).where(AuthSession.user_id == u.id)).scalars():
                s.revoked = True
    if body.unlock:
        u.locked_until, u.failed_logins = None, 0
        changes["unlocked"] = True
    audit.record(db, user, "user.updated", entity="user", entity_id=u.id, detail=changes)
    db.commit()
    return user_out(u)


@router.post("/clients/{client_id}/access", status_code=201)
def grant_access(client_id: int, body: AccessIn, user=Depends(current_user), db=Depends(get_db)):
    require_role(user, "admin")
    client = client_or_404(db, user, client_id)
    target = db.get(User, body.user_id)
    if target is None:
        raise HTTPException(404, "Not found.")
    if not db.execute(select(ClientAccess.id).where(ClientAccess.user_id == target.id,
                                                    ClientAccess.client_id == client.id)).first():
        db.add(ClientAccess(user_id=target.id, client_id=client.id))
        audit.record(db, user, "access.granted", client_id=client.id, entity="user", entity_id=target.id,
                     detail={"username": target.username, "role": target.role})
        db.commit()
    return {"ok": True}


@router.delete("/clients/{client_id}/access/{user_id}")
def revoke_access(client_id: int, user_id: int, user=Depends(current_user), db=Depends(get_db)):
    require_role(user, "admin")
    client = client_or_404(db, user, client_id)
    row = db.execute(select(ClientAccess).where(ClientAccess.user_id == user_id,
                                                ClientAccess.client_id == client.id)).scalar_one_or_none()
    if row is not None:
        db.delete(row)
        audit.record(db, user, "access.revoked", client_id=client.id, entity="user", entity_id=user_id)
        db.commit()
    return {"ok": True}


@router.get("/clients/{client_id}/team")
def team(client_id: int, user=Depends(current_user), db=Depends(get_db)):
    client = client_or_404(db, user, client_id)
    require_role(user, *INTERNAL)
    ids = set(db.execute(select(ClientAccess.user_id).where(ClientAccess.client_id == client.id)).scalars())
    users = db.execute(select(User).where(User.active.is_(True)).order_by(User.display_name)).scalars()
    return [user_out(u) for u in users if u.id in ids or u.role == "admin"]


# --- clients -----------------------------------------------------------------------------------------

@router.get("/clients")
def list_clients(user=Depends(current_user), db=Depends(get_db)):
    ids = accessible_client_ids(db, user)
    out = []
    for c in db.execute(select(Client).where(Client.id.in_(ids or [-1])).order_by(Client.code)).scalars():
        s = workflow.client_state(db, c)
        run = s["run"]
        out.append({**client_out(c), "stage": s["stage"], "ready_for_approval": s["ready_for_approval"],
                    "open_blockers": s["open_blockers"], "open_warnings": s["open_warnings"],
                    "latest_submission": s["latest_submission"], "latest_run_status": s["latest_run_status"],
                    "latest_decision": run.decision if run else None,
                    "checks_passed": sum(ch["ok"] for ch in s["checks"]), "checks_total": len(s["checks"])})
    return out


@router.post("/clients", status_code=201)
def create_client(body: ClientIn, user=Depends(current_user), db=Depends(get_db)):
    require_role(user, *ANALYSTS)
    c = workflow.create_client(db, user, body.code, body.name.strip(), body.go_live_target)
    db.commit()
    return client_out(c)


@router.get("/clients/{client_id}")
def get_client(client_id: int, user=Depends(current_user), db=Depends(get_db)):
    c = client_or_404(db, user, client_id)
    milestones = db.execute(select(Milestone).where(Milestone.client_id == c.id).order_by(Milestone.sort)).scalars()
    return {**client_out(c), "readiness": state_out(workflow.client_state(db, c)),
            "milestones": [milestone_out(m) for m in milestones]}


@router.patch("/clients/{client_id}")
def patch_client(client_id: int, body: ClientPatch, user=Depends(current_user), db=Depends(get_db)):
    c = client_or_404(db, user, client_id)
    require_role(user, *ANALYSTS)
    changes = {}
    if body.name is not None:
        changes["name"], c.name = [c.name, body.name], body.name
    if body.go_live_target is not None:
        changes["go_live_target"], c.go_live_target = [c.go_live_target, body.go_live_target], body.go_live_target
    if body.status is not None:
        if body.status not in ("onboarding", "on_hold"):
            raise HTTPException(422, "status can be set to onboarding or on_hold; 'live' is set by a completed export.")
        changes["status"], c.status = [c.status, body.status], body.status
    audit.record(db, user, "client.updated", client_id=c.id, entity="client", entity_id=c.id, detail=changes)
    db.commit()
    return client_out(c)


@router.get("/clients/{client_id}/readiness")
def readiness(client_id: int, user=Depends(current_user), db=Depends(get_db)):
    c = client_or_404(db, user, client_id)
    return state_out(workflow.client_state(db, c))


# --- rules -------------------------------------------------------------------------------------------

@router.get("/rules/baseline", response_class=PlainTextResponse)
def baseline_rules(user=Depends(current_user)):
    require_role(user, *INTERNAL)
    return RULES_PATH.read_text(encoding="utf-8")


@router.get("/clients/{client_id}/rulesets")
def list_rulesets(client_id: int, user=Depends(current_user), db=Depends(get_db)):
    c = client_or_404(db, user, client_id)
    require_role(user, *INTERNAL)
    who = names(db)
    rows = db.execute(select(RuleSet).where(RuleSet.client_id == c.id).order_by(RuleSet.version.desc())).scalars()
    return [ruleset_out(r, who) for r in rows]


@router.post("/clients/{client_id}/rulesets", status_code=201)
def draft_ruleset(client_id: int, body: RuleSetIn, user=Depends(current_user), db=Depends(get_db)):
    c = client_or_404(db, user, client_id)
    require_role(user, *ANALYSTS)
    rs = workflow.draft_rule_set(db, c, user, body.text, body.note)
    db.commit()
    return ruleset_out(rs, names(db))


@router.post("/rulesets/{ruleset_id}/review")
def review_ruleset(ruleset_id: int, body: ReviewIn, user=Depends(current_user), db=Depends(get_db)):
    rs = owned_or_404(db, user, RuleSet, ruleset_id)
    require_role(user, *APPROVERS)
    workflow.review_rule_set(db, rs, user, body.approve, body.comment)
    db.commit()
    return ruleset_out(rs, names(db))


# --- submissions -------------------------------------------------------------------------------------

def _safe_filename(name):
    base = os.path.basename((name or "upload.csv").replace("\\", "/"))
    return re.sub(r"[^\w.\- ]", "_", base)[:200] or "upload.csv"


@router.post("/clients/{client_id}/submissions", status_code=201)
def upload(client_id: int, request: Request, file: UploadFile = File(...), user=Depends(current_user),
           db=Depends(get_db)):
    c = client_or_404(db, user, client_id)
    require_role(user, "admin", "implementation_analyst", "client_contact")
    raw = file.file.read(MAX_FILE_BYTES + 1)
    try:
        sub, duplicate = processing.store_submission(db, state_of(request).store, c, user,
                                                     _safe_filename(file.filename), raw)
        db.commit()
    except IntegrityError:   # two uploads for this client at the same moment took the same sequence number
        db.rollback()
        sub = workflow.latest_submission(db, c.id)
        if sub is None or sub.sha256 != hashlib.sha256(raw).hexdigest():
            raise HTTPException(409, "Another upload for this client finished at the same moment. Upload again.")
        duplicate = True
    return {"submission": submission_out(sub), "duplicate": duplicate,
            "detail": ("This exact file is already the latest submission (#%d); it was not stored again."
                       % sub.sequence) if duplicate else "File received and stored encrypted."}


@router.get("/clients/{client_id}/submissions")
def list_submissions(client_id: int, user=Depends(current_user), db=Depends(get_db)):
    c = client_or_404(db, user, client_id)
    out = []
    for s in db.execute(select(Submission).where(Submission.client_id == c.id)
                        .order_by(Submission.sequence.desc())).scalars():
        run = workflow.latest_run(db, s.id)
        out.append({**submission_out(s), "run": reporting.run_summary(run)})
    return out


# --- mappings ----------------------------------------------------------------------------------------

@router.post("/submissions/{submission_id}/mappings", status_code=201)
def suggest_mapping(submission_id: int, body: SuggestIn, user=Depends(current_user), db=Depends(get_db)):
    sub = owned_or_404(db, user, Submission, submission_id)
    require_role(user, *ANALYSTS)
    if sub.header_error:
        raise HTTPException(409, "The file's header could not be read: " + sub.header_error)
    client = db.get(Client, sub.client_id)
    rs = workflow.current_rule_set(db, client.id)
    specs = parse_rules(rs.text)
    templates = db.execute(select(MappingTemplate).order_by(MappingTemplate.id.desc())).scalars().all()
    result = suggest(sub.headers, specs, templates, use_ai=body.use_ai)
    m = workflow.start_mapping(db, client, user, sub, result)
    db.commit()
    return {**mapping_out(m, names(db)), "ai_used": result["ai_used"], "ai_error": result["ai_error"],
            "template": result["template"]}


@router.get("/clients/{client_id}/mappings")
def list_mappings(client_id: int, user=Depends(current_user), db=Depends(get_db)):
    c = client_or_404(db, user, client_id)
    require_role(user, *INTERNAL)
    who = names(db)
    return [mapping_out(m, who) for m in db.execute(select(Mapping).where(Mapping.client_id == c.id)
                                                    .order_by(Mapping.version.desc())).scalars()]


@router.get("/mappings/{mapping_id}")
def get_mapping(mapping_id: int, user=Depends(current_user), db=Depends(get_db)):
    m = owned_or_404(db, user, Mapping, mapping_id)
    require_role(user, *INTERNAL)
    return mapping_out(m, names(db))


@router.put("/mappings/{mapping_id}")
def put_mapping(mapping_id: int, body: MappingPut, user=Depends(current_user), db=Depends(get_db)):
    m = owned_or_404(db, user, Mapping, mapping_id)
    require_role(user, *ANALYSTS)
    if m.status not in ("draft", "rejected"):
        raise HTTPException(409, f"Only draft mappings can be edited; this one is {m.status}.")
    specs = parse_rules(workflow.current_rule_set(db, m.client_id).text)
    problems, corrections, unconfirmed = check_mapping(m.headers, specs, m.suggestions, body.mapping,
                                                       body.confirmed_fields)
    hard = [p for p in problems if not p.startswith("Confirm these fields") and not p.startswith("Required fields")]
    if hard or (body.submit and problems):
        raise HTTPException(422, {"message": " ".join(problems), "unconfirmed_fields": unconfirmed})
    m.mapping = {f: (body.mapping.get(f) or None) for f in specs}
    m.confirmed_fields = sorted(set(body.confirmed_fields) & set(specs))
    m.corrections, m.note, m.author_id = corrections, body.note, user.id
    if body.submit:
        m.status = "pending_approval"
    audit.record(db, user, "mapping.submitted" if body.submit else "mapping.saved", client_id=m.client_id,
                 entity="mapping", entity_id=m.id,
                 detail={"version": m.version, "corrections": corrections, "confirmed_fields": m.confirmed_fields})
    db.commit()
    return mapping_out(m, names(db))


@router.post("/mappings/{mapping_id}/review")
def review_mapping(mapping_id: int, body: ReviewIn, user=Depends(current_user), db=Depends(get_db)):
    m = owned_or_404(db, user, Mapping, mapping_id)
    require_role(user, *APPROVERS)
    workflow.review_mapping(db, m, user, body.approve, body.comment)
    db.commit()
    return mapping_out(m, names(db))


@router.post("/mappings/{mapping_id}/template", status_code=201)
def save_template(mapping_id: int, body: TemplateIn, user=Depends(current_user), db=Depends(get_db)):
    m = owned_or_404(db, user, Mapping, mapping_id)
    require_role(user, *ANALYSTS)
    t = workflow.save_template(db, m, user, body.name.strip())
    db.commit()
    return {"id": t.id, "name": t.name, "headers": t.headers, "mapping": t.mapping}


@router.get("/templates")
def list_templates(user=Depends(current_user), db=Depends(get_db)):
    require_role(user, *INTERNAL)
    return [{"id": t.id, "name": t.name, "headers": t.headers, "mapping": t.mapping, "created_at": t.created_at}
            for t in db.execute(select(MappingTemplate).order_by(MappingTemplate.name)).scalars()]


# --- validation runs ---------------------------------------------------------------------------------

@router.post("/submissions/{submission_id}/runs", status_code=202)
def start_run(submission_id: int, request: Request, background: BackgroundTasks, user=Depends(current_user),
              db=Depends(get_db)):
    sub = owned_or_404(db, user, Submission, submission_id)
    require_role(user, *ANALYSTS)
    run = processing.create_run(db, db.get(Client, sub.client_id), sub, user)
    db.commit()
    background.add_task(processing.process_run, state_of(request), run.id)
    return reporting.run_summary(run)


@router.get("/runs/{run_id}")
def get_run(run_id: int, user=Depends(current_user), db=Depends(get_db)):
    run = owned_or_404(db, user, ValidationRun, run_id)
    out = reporting.run_summary(run)
    if user.role != "client_contact":
        out["facts"] = run.facts
    elif run.facts:
        out["findings_by_rule"] = run.facts["findings_by_rule"]
    return out


@router.post("/runs/{run_id}/retry", status_code=202)
def retry_run(run_id: int, request: Request, background: BackgroundTasks, user=Depends(current_user),
              db=Depends(get_db)):
    run = owned_or_404(db, user, ValidationRun, run_id)
    require_role(user, *ANALYSTS)
    processing.retry_run(db, run, user)
    db.commit()
    background.add_task(processing.process_run, state_of(request), run.id)
    return reporting.run_summary(run)


@router.get("/runs/{run_id}/findings")
def run_findings(run_id: int, request: Request, severity: Optional[str] = None, field: Optional[str] = None,
                 offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000),
                 user=Depends(current_user), db=Depends(get_db)):
    run = owned_or_404(db, user, ValidationRun, run_id)
    q = select(Finding).where(Finding.run_id == run.id)
    if severity:
        q = q.where(Finding.severity == severity)
    if field:
        q = q.where(Finding.field == field)
    total = db.execute(select(func.count()).select_from(q.subquery())).scalar()
    cipher = state_of(request).cipher
    rows = db.execute(q.order_by(Finding.line, Finding.id).offset(offset).limit(limit)).scalars()
    return {"total": total, "stored": run.findings_stored, "counted": (run.blockers or 0) + (run.warnings or 0),
            "items": [{"line": f.line, "field": f.field, "client_column": f.client_column,
                       "entered": cipher.decrypt_text(f.entered_enc), "rule": f.rule, "severity": f.severity,
                       "message": f.message} for f in rows]}


@router.get("/runs/{run_id}/findings.csv")
def run_findings_csv(run_id: int, request: Request, user=Depends(current_user), db=Depends(get_db)):
    run = owned_or_404(db, user, ValidationRun, run_id)
    text = reporting.findings_csv_text(reporting.findings_rows(db, state_of(request).cipher, run.id))
    audit.record(db, user, "findings.downloaded", client_id=run.client_id, entity="run", entity_id=run.id)
    db.commit()
    return Response(text, media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="findings-run-{run.id}.csv"'})


@router.get("/runs/{run_id}/report.md", response_class=PlainTextResponse)
def run_report(run_id: int, user=Depends(current_user), db=Depends(get_db)):
    run = owned_or_404(db, user, ValidationRun, run_id)
    require_role(user, *INTERNAL)
    if not run.facts:
        raise HTTPException(409, "This run has not completed.")
    from claims_onboarding.readiness import markdown_report, written_summary
    return markdown_report(run.facts, written_summary(run.facts))


# --- exceptions --------------------------------------------------------------------------------------

@router.get("/clients/{client_id}/exceptions")
def list_exceptions(client_id: int, status: Optional[str] = None, severity: Optional[str] = None,
                    user=Depends(current_user), db=Depends(get_db)):
    c = client_or_404(db, user, client_id)
    q = select(ExceptionItem).where(ExceptionItem.client_id == c.id)
    if status == "open":
        q = q.where(ExceptionItem.status.in_(workflow.OPEN_STATES))
    elif status:
        q = q.where(ExceptionItem.status == status)
    if severity:
        q = q.where(ExceptionItem.severity == severity)
    who = names(db)
    rows = db.execute(q).scalars().all()
    rows.sort(key=lambda e: (e.status == "resolved", e.severity != BLOCKER, -e.current_count, e.id))
    return [exception_out(e, who) for e in rows]


@router.get("/exceptions/{exception_id}")
def get_exception(exception_id: int, user=Depends(current_user), db=Depends(get_db)):
    e = owned_or_404(db, user, ExceptionItem, exception_id)
    who = names(db)
    events = db.execute(select(ExceptionEvent).where(ExceptionEvent.exception_id == e.id)
                        .order_by(ExceptionEvent.id)).scalars()
    return {**exception_out(e, who), "events": [{"at": ev.at, "kind": ev.kind, "actor": who.get(ev.actor_id, "system"),
                                                 "detail": ev.detail} for ev in events]}


@router.patch("/exceptions/{exception_id}")
def patch_exception(exception_id: int, body: ExceptionPatch, user=Depends(current_user), db=Depends(get_db)):
    e = owned_or_404(db, user, ExceptionItem, exception_id)
    changing = body.owner_id is not None or body.clear_owner or body.status is not None
    if changing:
        require_role(user, *INTERNAL)
    elif not body.note.strip():
        raise HTTPException(422, "Nothing to change.")
    detail = {}
    if body.owner_id is not None:
        owner = db.get(User, body.owner_id)
        if owner is None or not owner.active or not can_access(db, owner, e.client_id):
            raise HTTPException(422, "The owner must be an active user with access to this client.")
        detail["owner"], e.owner_id = [e.owner_id, owner.id], owner.id
    if body.clear_owner:
        detail["owner"], e.owner_id = [e.owner_id, None], None
    if body.status is not None and body.status != e.status:
        new = body.status
        if new == "resolved":
            raise HTTPException(409, "Exceptions are resolved automatically when a resubmitted file no longer "
                                     "contains them. Ask the client to correct and resend the file.")
        if new == "accepted":
            if e.severity == BLOCKER:
                raise HTTPException(409, "Blockers cannot be accepted or waived. They are cleared only by a "
                                         "corrected file.")
            require_role(user, *APPROVERS)
            if len(body.note.strip()) < 10:
                raise HTTPException(422, "Accepting a warning needs a note of at least 10 characters saying why.")
        elif new in ("open", "in_progress"):
            if e.status == "resolved":
                raise HTTPException(409, "A resolved exception reopens automatically if a later file contains it again.")
            if e.status == "accepted":
                require_role(user, *APPROVERS)
        else:
            raise HTTPException(422, "status must be open, in_progress or accepted.")
        detail["status"], e.status = [e.status, new], new
        if new == "accepted":
            e.resolution = body.note.strip()
    if body.note.strip():
        detail["note"] = body.note.strip()
    e.updated_at = utcnow()
    db.add(ExceptionEvent(exception_id=e.id, actor_id=user.id, kind="updated" if changing else "note", detail=detail))
    audit.record(db, user, "exception.updated" if changing else "exception.note", client_id=e.client_id,
                 entity="exception", entity_id=e.id, detail=detail)
    db.commit()
    return exception_out(e, names(db))


@router.get("/exceptions/{exception_id}/explanation")
def explain_exception(exception_id: int, ai: bool = False, user=Depends(current_user), db=Depends(get_db)):
    e = owned_or_404(db, user, ExceptionItem, exception_id)
    rs = workflow.current_rule_set(db, e.client_id)
    base = comms.explanation(e, parse_rules(rs.text))
    out = {**base, "ai_text": None, "ai_error": None}
    if ai:
        require_role(user, *INTERNAL)   # AI calls are made for the implementation team, not by client contacts
        try:
            out["ai_text"] = comms.ai_explanation(e, base)
        except ExplanationError as exc:
            out["ai_error"] = ai_error_text(exc)
    return out


@router.get("/clients/{client_id}/resubmissions")
def resubmissions(client_id: int, user=Depends(current_user), db=Depends(get_db)):
    c = client_or_404(db, user, client_id)
    return reporting.resubmission_history(db, c)


# --- go-live -----------------------------------------------------------------------------------------

@router.post("/clients/{client_id}/golive", status_code=201)
def go_live(client_id: int, body: ReviewIn, user=Depends(current_user), db=Depends(get_db)):
    c = client_or_404(db, user, client_id)
    require_role(user, *APPROVERS)
    a = workflow.decide_go_live(db, c, user, body.approve, body.comment)
    db.commit()
    return {"id": a.id, "decision": a.decision, "run_id": a.run_id, "checklist": a.checklist, "at": a.at}


@router.get("/clients/{client_id}/approvals")
def approvals(client_id: int, user=Depends(current_user), db=Depends(get_db)):
    c = client_or_404(db, user, client_id)
    require_role(user, *INTERNAL)
    who = names(db)
    return [{"id": a.id, "run_id": a.run_id, "decision": a.decision, "comment": a.comment,
             "approver": who.get(a.approver_id), "checklist": a.checklist, "at": a.at, "active": a.active}
            for a in db.execute(select(Approval).where(Approval.client_id == c.id).order_by(Approval.id.desc())).scalars()]


@router.post("/clients/{client_id}/exports", status_code=202)
def export(client_id: int, request: Request, background: BackgroundTasks, user=Depends(current_user),
           db=Depends(get_db)):
    c = client_or_404(db, user, client_id)
    require_role(user, *ANALYSTS)
    try:
        exp, existing = downstream.start_export(db, c, user, state_of(request).settings.export_batch_size)
        db.commit()
    except IntegrityError:   # two export requests for the same approved run at the same moment
        db.rollback()
        exp, existing = downstream.start_export(db, c, user, state_of(request).settings.export_batch_size)
    if not existing:
        background.add_task(downstream.run_export, state_of(request), exp.id)
    return {**export_out(exp), "existing": existing}


@router.post("/exports/{export_id}/retry", status_code=202)
def retry_export(export_id: int, request: Request, background: BackgroundTasks, user=Depends(current_user),
                 db=Depends(get_db)):
    exp = owned_or_404(db, user, Export, export_id)
    require_role(user, *ANALYSTS)
    downstream.retry_export(db, exp, user)
    db.commit()
    background.add_task(downstream.run_export, state_of(request), exp.id)
    return export_out(exp)


@router.get("/clients/{client_id}/exports")
def list_exports(client_id: int, user=Depends(current_user), db=Depends(get_db)):
    c = client_or_404(db, user, client_id)
    require_role(user, *INTERNAL)
    return [export_out(x) for x in db.execute(select(Export).where(Export.client_id == c.id)
                                              .order_by(Export.id.desc())).scalars()]


@router.get("/clients/{client_id}/evidence")
def evidence(client_id: int, request: Request, user=Depends(current_user), db=Depends(get_db)):
    c = client_or_404(db, user, client_id)
    require_role(user, *INTERNAL)
    data, digest = reporting.evidence_package(db, state_of(request).cipher, c, user)
    db.commit()
    return Response(data, media_type="application/zip", headers={
        "Content-Disposition": f'attachment; filename="{c.code}-go-live-evidence.zip"', "X-Manifest-SHA256": digest})


# --- communication and timeline ---------------------------------------------------------------------

@router.get("/clients/{client_id}/communications")
def list_comms(client_id: int, user=Depends(current_user), db=Depends(get_db)):
    c = client_or_404(db, user, client_id)
    q = select(Communication).where(Communication.client_id == c.id)
    if user.role == "client_contact":
        q = q.where(Communication.status == "sent")
    who = names(db)
    return [comm_out(x, who) for x in db.execute(q.order_by(Communication.id.desc())).scalars()]


@router.post("/clients/{client_id}/communications", status_code=201)
def draft_comm(client_id: int, body: CommIn, request: Request, user=Depends(current_user), db=Depends(get_db)):
    c = client_or_404(db, user, client_id)
    require_role(user, *ANALYSTS)
    cipher = state_of(request).cipher
    x = comms.draft(db, cipher, c, user, body.kind, body.subject, body.body)
    db.commit()
    return comm_out(x, names(db), cipher)


@router.get("/communications/{comm_id}")
def get_comm(comm_id: int, request: Request, user=Depends(current_user), db=Depends(get_db)):
    x = owned_or_404(db, user, Communication, comm_id)
    if user.role == "client_contact" and x.status != "sent":
        raise HTTPException(404, "Not found.")
    return comm_out(x, names(db), state_of(request).cipher)


@router.post("/communications/{comm_id}/send")
def send_comm(comm_id: int, user=Depends(current_user), db=Depends(get_db)):
    x = owned_or_404(db, user, Communication, comm_id)
    require_role(user, *INTERNAL)
    comms.send(db, x, user)
    db.commit()
    return comm_out(x, names(db))


def milestone_out(m):
    return {"id": m.id, "key": m.key, "name": m.name, "sort": m.sort, "due_date": m.due_date, "status": m.status,
            "completed_at": m.completed_at}


@router.get("/clients/{client_id}/milestones")
def milestones(client_id: int, user=Depends(current_user), db=Depends(get_db)):
    c = client_or_404(db, user, client_id)
    return [milestone_out(m) for m in db.execute(select(Milestone).where(Milestone.client_id == c.id)
                                                 .order_by(Milestone.sort)).scalars()]


@router.patch("/milestones/{milestone_id}")
def patch_milestone(milestone_id: int, body: MilestonePatch, user=Depends(current_user), db=Depends(get_db)):
    m = owned_or_404(db, user, Milestone, milestone_id)
    require_role(user, *ANALYSTS)
    detail = {}
    if body.status is not None:
        if body.status not in ("not_started", "in_progress", "done", "blocked"):
            raise HTTPException(422, "Unknown milestone status.")
        detail["status"], m.status = [m.status, body.status], body.status
        m.completed_at = utcnow() if body.status == "done" else None
    if body.due_date is not None:
        detail["due_date"], m.due_date = [m.due_date, body.due_date], body.due_date
    audit.record(db, user, "milestone.updated", client_id=m.client_id, entity="milestone", entity_id=m.id,
                 detail={"key": m.key, **detail})
    db.commit()
    return milestone_out(m)


# --- reporting and audit -----------------------------------------------------------------------------

@router.get("/clients/{client_id}/scorecard")
def scorecard(client_id: int, user=Depends(current_user), db=Depends(get_db)):
    c = client_or_404(db, user, client_id)
    require_role(user, *INTERNAL)
    return reporting.scorecard(db, c)


@router.get("/reports/portfolio")
def portfolio(user=Depends(current_user), db=Depends(get_db)):
    require_role(user, *INTERNAL)
    return reporting.portfolio(db, accessible_client_ids(db, user))


@router.get("/metrics/processing")
def processing_metrics(user=Depends(current_user), db=Depends(get_db)):
    require_role(user, *INTERNAL)
    return reporting.processing_metrics(db, accessible_client_ids(db, user))


@router.get("/clients/{client_id}/audit")
def client_audit(client_id: int, limit: int = Query(200, ge=1, le=2000), user=Depends(current_user),
                 db=Depends(get_db)):
    c = client_or_404(db, user, client_id)
    require_role(user, *INTERNAL)
    rows = db.execute(select(AuditEntry).where(AuditEntry.client_id == c.id).order_by(AuditEntry.id.desc())
                      .limit(limit)).scalars()
    return [{"id": a.id, "at": a.at, "actor": a.actor, "action": a.action, "entity": a.entity,
             "entity_id": a.entity_id, "detail": a.detail, "hash": a.hash} for a in rows]


@router.get("/audit/verify")
def verify_audit(user=Depends(current_user), db=Depends(get_db)):
    require_role(user, "admin")
    return audit.verify(db)


# --- simulation (operational-failure scenarios) ------------------------------------------------------

@router.put("/admin/simulation")
def simulation(body: SimulationIn, request: Request, user=Depends(current_user), db=Depends(get_db)):
    require_role(user, "admin")
    if not state_of(request).settings.simulation_enabled:
        raise HTTPException(404, "Not found.")
    fault = body.downstream_fault
    if fault is not None and fault.get("mode") not in ("transient", "outage", "lost_ack"):
        raise HTTPException(422, "mode must be transient, outage or lost_ack.")
    downstream.set_fault(db, user, fault)
    for key in ("fail_next_run", "hold_next_run"):
        row = db.get(Setting, key)
        armed = getattr(body, key)
        if row is None:
            db.add(Setting(key=key, value={"armed": armed}))
        else:
            row.value = {"armed": armed}
    audit.record(db, user, "simulation.updated", detail={"fail_next_run": body.fail_next_run,
                                                         "hold_next_run": body.hold_next_run})
    db.commit()
    return {"downstream_fault": fault, "fail_next_run": body.fail_next_run, "hold_next_run": body.hold_next_run}


@router.post("/admin/recover")
def recover(user=Depends(current_user), db=Depends(get_db)):
    require_role(user, "admin")
    result = processing.recover_interrupted(db)
    db.commit()
    return result


@router.get("/admin/downstream/{client_id}")
def downstream_summary(client_id: int, user=Depends(current_user), db=Depends(get_db)):
    require_role(user, "admin")
    c = client_or_404(db, user, client_id)
    records = db.execute(select(func.count(DownstreamRecord.id)).where(DownstreamRecord.client_id == c.id)).scalar()
    distinct = db.execute(select(func.count(func.distinct(DownstreamRecord.claim_id)))
                          .where(DownstreamRecord.client_id == c.id)).scalar()
    batches = db.execute(select(func.count(DownstreamBatch.id)).where(DownstreamBatch.client_id == c.id)).scalar()
    return {"records": records, "distinct_claim_ids": distinct, "batches": batches}
