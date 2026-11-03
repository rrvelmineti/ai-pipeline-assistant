"""Profile-driven CSV validation and session-scoped transactional loads."""
import csv
import hashlib
import io
import json
import re
import sqlite3
from contextlib import closing
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from .core import MAX_BYTES, MAX_ROWS


class Rule(BaseModel):
    kind: Literal["text", "integer", "decimal", "date"]
    required: bool = True
    unique: bool = False
    minimum: int = 0
    maximum: int = 1_000_000


PROFILES = {
    "orders": {"quantity": Rule(kind="integer", minimum=1), "unit_price": Rule(kind="decimal")},
    "inventory": {"sku": Rule(kind="text", unique=True), "stock": Rule(kind="integer"),
                  "as_of": Rule(kind="date", required=False)},
}


class Run(BaseModel):
    schema_version: Literal[2] = 2
    run_id: str = Field(default_factory=lambda: str(uuid4()))
    profile: Literal["orders", "inventory"]
    stage: str = "ingestion"
    stages: list[str] = Field(default_factory=lambda: ["ingestion"])
    code: str = "ok"
    row: int | None = None
    field: str | None = None
    rows_validated: int = 0
    source_sha256: str
    total_cents: int | None = None
    already_loaded: bool = False

    def enter(self, stage):
        self.stage = stage
        self.stages.append(stage)


class Invalid(ValueError):
    pass


def convert(raw, rule):
    value = raw.strip()
    if not value:
        if rule.required:
            raise Invalid("missing_value")
        return None
    if rule.kind == "text":
        return value
    if rule.kind == "date":
        try:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                raise ValueError
            return date.fromisoformat(value).isoformat()
        except ValueError:
            raise Invalid("invalid_date") from None
    pattern = r"[0-9]{1,7}" if rule.kind == "integer" else r"[0-9]{1,7}(?:\.[0-9]{1,2})?"
    if not re.fullmatch(pattern, value):
        raise Invalid("invalid_number")
    number = Decimal(value)
    if not rule.minimum <= number <= rule.maximum:
        raise Invalid("invalid_number")
    return int(number) if rule.kind == "integer" else number


def reader_for(raw):
    return csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline=""), strict=True)


def load_orders(db, batch, rows):
    with closing(sqlite3.connect(db, timeout=2)) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("CREATE TABLE IF NOT EXISTS imports (id TEXT PRIMARY KEY, digest TEXT UNIQUE)")
        conn.execute("CREATE TABLE IF NOT EXISTS orders (batch TEXT, quantity INTEGER, cents INTEGER)")
        existing = conn.execute("SELECT id FROM imports WHERE digest=?", (batch,)).fetchone()
        if not existing:
            conn.execute("INSERT INTO imports VALUES (?,?)", (batch, batch))
            conn.executemany("INSERT INTO orders VALUES (?,?,?)", ((batch, q, p) for q, p in rows))
        total, = conn.execute("SELECT SUM(quantity*cents) FROM orders WHERE batch=?", (batch,)).fetchone()
        return bool(existing), total


def process(raw, profile, mapping, db, *, limits=None):
    digest = hashlib.sha256(raw).hexdigest()
    run = Run(profile=profile, source_sha256=digest)
    rules = dict(PROFILES[profile])
    try:
        if len(raw) > MAX_BYTES:
            raise Invalid("input_limit")
        for field, (low, high) in (limits or {}).items():
            rule = rules.get(field)
            if rule is None or rule.kind not in {"integer", "decimal"} or not rule.minimum <= low <= high <= rule.maximum:
                raise Invalid("invalid_mapping")
            rules[field] = rule.model_copy(update={"minimum": low, "maximum": high})
        reader = reader_for(raw)
        headers = next(reader, [])
        run.enter("validation")
        selected = list(mapping.values())
        if (len(headers) != len(set(headers)) or set(mapping) - set(rules)
                or any(key not in mapping for key, rule in rules.items() if rule.required)
                or len(selected) != len(set(selected)) or not set(selected) <= set(headers)):
            raise Invalid("invalid_mapping")
        indexes = {field: headers.index(name) for field, name in mapping.items()}
        seen = {field: set() for field, rule in rules.items() if rule.unique}
        rows = []
        for values in reader:
            run.row = reader.line_num
            if run.rows_validated >= MAX_ROWS:
                raise Invalid("input_limit")
            if len(values) != len(headers):
                raise Invalid("invalid_csv")
            parsed = {}
            for field, index in indexes.items():
                run.field = field
                value = convert(values[index], rules[field])
                if field in seen and value is not None:
                    if value in seen[field]:
                        raise Invalid("duplicate")
                    seen[field].add(value)
                parsed[field] = value
            rows.append(parsed)
            run.field = None
            run.rows_validated += 1
        if not rows:
            raise Invalid("empty_file")
        run.row = None
        if profile == "orders":
            run.enter("transformation")
            orders = [(r["quantity"], int(r["unit_price"] * 100)) for r in rows]
            batch = hashlib.sha256(json.dumps([digest, mapping], sort_keys=True).encode()).hexdigest()
            run.enter("load")
            run.already_loaded, run.total_cents = load_orders(db, batch, orders)
        run.enter("completed")
    except Invalid as exc:
        run.code = str(exc)
    except (csv.Error, UnicodeError):
        run.code = "invalid_csv"
    except sqlite3.Error:
        run.code = "database_failure"
    return run


def stored_count(db):
    if not Path(db).is_file():
        return 0
    with closing(sqlite3.connect(Path(db).resolve().as_uri() + "?mode=ro", uri=True)) as conn:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='orders'").fetchone():
            return 0
        return conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
