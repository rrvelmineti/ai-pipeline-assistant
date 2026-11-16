"""Database tables. Every client-owned row carries client_id so access can be checked in one place."""
from datetime import date, datetime

from sqlalchemy import (JSON, Boolean, Date, DateTime, ForeignKey, Index, Integer, LargeBinary, String, Text,
                        UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, utcnow

ROLES = ("admin", "implementation_analyst", "approver", "client_contact")


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True)
    display_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(40))
    password_hash: Mapped[str] = mapped_column(String(300))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class Client(Base):
    __tablename__ = "clients"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(30), default="onboarding")  # onboarding, live, on_hold
    go_live_target: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ClientAccess(Base):
    __tablename__ = "client_access"
    __table_args__ = (UniqueConstraint("user_id", "client_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))


class RuleSet(Base):
    """A versioned copy of the plain-language rules for one client. Only an approved version is used."""
    __tablename__ = "rule_sets"
    __table_args__ = (UniqueConstraint("client_id", "version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    version: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft, approved, superseded, rejected
    note: Mapped[str] = mapped_column(String(500), default="")
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approver_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Mapping(Base):
    """Client column -> target field, with the suggestion, its confidence and every human decision."""
    __tablename__ = "mappings"
    __table_args__ = (UniqueConstraint("client_id", "version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    version: Mapped[int] = mapped_column(Integer)
    submission_id: Mapped[int | None] = mapped_column(ForeignKey("submissions.id"), nullable=True)
    headers: Mapped[list] = mapped_column(JSON)
    suggestions: Mapped[dict] = mapped_column(JSON)
    mapping: Mapped[dict] = mapped_column(JSON)
    confirmed_fields: Mapped[list] = mapped_column(JSON, default=list)
    corrections: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft, approved, superseded, rejected
    note: Mapped[str] = mapped_column(String(500), default="")
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approver_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    review_comment: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class MappingTemplate(Base):
    """A reusable mapping: column headings and target fields only, with no client data."""
    __tablename__ = "mapping_templates"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    headers: Mapped[list] = mapped_column(JSON)
    mapping: Mapped[dict] = mapped_column(JSON)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Submission(Base):
    __tablename__ = "submissions"
    __table_args__ = (UniqueConstraint("client_id", "sequence"), Index("ix_submissions_sha", "client_id", "sha256"))
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    sequence: Mapped[int] = mapped_column(Integer)
    filename: Mapped[str] = mapped_column(String(200))
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer)
    headers: Mapped[list] = mapped_column(JSON)
    header_error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    storage_key: Mapped[str] = mapped_column(String(200))
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ValidationRun(Base):
    __tablename__ = "validation_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    submission_id: Mapped[int] = mapped_column(ForeignKey("submissions.id"))
    mapping_id: Mapped[int] = mapped_column(ForeignKey("mappings.id"))
    rule_set_id: Mapped[int] = mapped_column(ForeignKey("rule_sets.id"))
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued, running, completed, failed, interrupted
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    as_of: Mapped[date] = mapped_column(Date)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    queued_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rows_checked: Mapped[int | None] = mapped_column(Integer, nullable=True)
    blockers: Mapped[int | None] = mapped_column(Integer, nullable=True)
    warnings: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scan_complete: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    decision: Mapped[str | None] = mapped_column(String(20), nullable=True)
    facts: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    findings_stored: Mapped[int] = mapped_column(Integer, default=0)


class Finding(Base):
    __tablename__ = "findings"
    __table_args__ = (Index("ix_findings_run", "run_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("validation_runs.id"))
    line: Mapped[int] = mapped_column(Integer)
    field: Mapped[str] = mapped_column(String(80))
    client_column: Mapped[str] = mapped_column(String(200))
    rule: Mapped[str] = mapped_column(String(200))
    severity: Mapped[str] = mapped_column(String(20))
    message: Mapped[str] = mapped_column(String(300))
    entered_enc: Mapped[bytes] = mapped_column(LargeBinary)  # the cell value, encrypted at rest


class ExceptionItem(Base):
    """One open problem for a client: a (field, rule, severity) group, tracked across resubmissions."""
    __tablename__ = "exceptions"
    __table_args__ = (UniqueConstraint("client_id", "field", "rule", "severity"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    field: Mapped[str] = mapped_column(String(80))
    client_column: Mapped[str] = mapped_column(String(200), default="")
    rule: Mapped[str] = mapped_column(String(200))
    severity: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="open")  # open, in_progress, resolved, reopened, accepted
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    resolution: Mapped[str] = mapped_column(String(500), default="")
    first_count: Mapped[int] = mapped_column(Integer)
    current_count: Mapped[int] = mapped_column(Integer)
    first_run_id: Mapped[int] = mapped_column(ForeignKey("validation_runs.id"))
    last_run_id: Mapped[int] = mapped_column(ForeignKey("validation_runs.id"))
    first_submission: Mapped[int] = mapped_column(Integer)
    last_submission: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ExceptionEvent(Base):
    __tablename__ = "exception_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    exception_id: Mapped[int] = mapped_column(ForeignKey("exceptions.id"))
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(30))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


class Approval(Base):
    __tablename__ = "approvals"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    run_id: Mapped[int] = mapped_column(ForeignKey("validation_runs.id"))
    decision: Mapped[str] = mapped_column(String(20))  # approved, rejected
    comment: Mapped[str] = mapped_column(String(1000), default="")
    approver_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    checklist: Mapped[dict] = mapped_column(JSON)
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class AuditEntry(Base):
    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_client", "client_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actor: Mapped[str] = mapped_column(String(80))
    action: Mapped[str] = mapped_column(String(60))
    client_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    entity: Mapped[str] = mapped_column(String(40), default="")
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))


class AuditHead(Base):
    """One row holding the latest audit hash; locked while appending so the chain cannot fork."""
    __tablename__ = "audit_head"
    id: Mapped[int] = mapped_column(primary_key=True)
    last_hash: Mapped[str] = mapped_column(String(64))
    entries: Mapped[int] = mapped_column(Integer, default=0)


class Export(Base):
    __tablename__ = "exports"
    __table_args__ = (UniqueConstraint("run_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    run_id: Mapped[int] = mapped_column(ForeignKey("validation_runs.id"))
    approval_id: Mapped[int] = mapped_column(ForeignKey("approvals.id"))
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending, in_progress, completed, failed
    batch_size: Mapped[int] = mapped_column(Integer)
    total_records: Mapped[int] = mapped_column(Integer, default=0)
    batches_total: Mapped[int] = mapped_column(Integer, default=0)
    batches_done: Mapped[int] = mapped_column(Integer, default=0)
    sent_records: Mapped[int] = mapped_column(Integer, default=0)
    skipped_duplicates: Mapped[int] = mapped_column(Integer, default=0)
    batch_retries: Mapped[int] = mapped_column(Integer, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)


class DownstreamBatch(Base):
    """Simulated downstream claims system: batches it has accepted, keyed for idempotent replays."""
    __tablename__ = "downstream_batches"
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_key: Mapped[str] = mapped_column(String(64), unique=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    export_id: Mapped[int] = mapped_column(ForeignKey("exports.id"))
    accepted: Mapped[int] = mapped_column(Integer)
    duplicates: Mapped[int] = mapped_column(Integer)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class DownstreamRecord(Base):
    """Simulated downstream claims system: one row per claim. A claim can be loaded once per client."""
    __tablename__ = "downstream_records"
    __table_args__ = (UniqueConstraint("client_id", "claim_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    claim_id: Mapped[str] = mapped_column(String(120))
    batch_key: Mapped[str] = mapped_column(String(64))
    payload_enc: Mapped[bytes] = mapped_column(LargeBinary)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Milestone(Base):
    __tablename__ = "milestones"
    __table_args__ = (UniqueConstraint("client_id", "key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    key: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(120))
    sort: Mapped[int] = mapped_column(Integer)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="not_started")  # not_started, in_progress, done, blocked
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Communication(Base):
    __tablename__ = "communications"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    run_id: Mapped[int | None] = mapped_column(ForeignKey("validation_runs.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(30))  # issue_letter, resubmission_summary, note
    subject: Mapped[str] = mapped_column(String(200))
    body_enc: Mapped[bytes] = mapped_column(LargeBinary)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft, sent
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    sent_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)
