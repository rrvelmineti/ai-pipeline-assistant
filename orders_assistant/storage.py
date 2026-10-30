"""Local audit history and atomic latest-result snapshots."""
import json
import os
import sqlite3
import tempfile
from pathlib import Path


def save_json(record, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         delete=False, suffix=".tmp") as target:
            name = target.name
            json.dump(record, target, indent=2, allow_nan=False)
            target.write("\n")
        os.replace(name, path)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


def save_run(record, database):
    Path(database).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, record TEXT NOT NULL)")
        db.execute("INSERT INTO runs VALUES (?, ?, ?)",
                   (record["run_id"], record["created_at"], json.dumps(record, allow_nan=False)))


def history(database, limit=20):
    if not Path(database).is_file():
        return []
    with sqlite3.connect(database) as db:
        rows = db.execute("SELECT record FROM runs ORDER BY created_at DESC LIMIT ?", (limit,))
        return [json.loads(row[0]) for row in rows]
