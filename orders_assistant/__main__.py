"""Command-line interface; run python -m orders_assistant --help."""
import argparse
import json
import sqlite3
import sys
from pathlib import Path
from .core import analyze
from .explain import explain, gemini_explain, ExplanationError
from .storage import save_json, save_run, history


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate orders and explain evidence without inventing repairs.")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="Validate CSV and save a new run")
    run.add_argument("csv", type=Path)
    run.add_argument("--output", type=Path, default=Path("local_data/latest.json"))
    run.add_argument("--database", type=Path, default=Path("local_data/runs.sqlite3"))
    show = commands.add_parser("explain", help="Explain a saved run; does not rerun CSV")
    show.add_argument("record", type=Path, nargs="?", default=Path("local_data/latest.json"))
    show.add_argument("--provider", choices=["offline", "gemini"], default="offline")
    logs = commands.add_parser("history", help="Show local run history")
    logs.add_argument("--database", type=Path, default=Path("local_data/runs.sqlite3"))
    logs.add_argument("--limit", type=int, default=20)
    args = parser.parse_args(argv)
    try:
        if args.command == "run":
            resolved = [args.csv.resolve(), args.output.resolve(), args.database.resolve()]
            if len(set(resolved)) != 3:
                parser.error("CSV, output, and database paths must be different.")
            record = analyze(args.csv)
            # History is committed first; a snapshot failure cannot discard the audit record.
            save_run(record, args.database)
            save_json(record, args.output)
            print(json.dumps(record, indent=2))
            return 0 if record["status"] == "success" else 1
        if args.command == "history":
            if not 1 <= args.limit <= 1000:
                parser.error("--limit must be between 1 and 1000")
            print(json.dumps(history(args.database, args.limit), indent=2))
            return 0
        record = json.loads(args.record.read_text(encoding="utf-8"))
        if not isinstance(record, dict):
            raise ExplanationError("Run record must be a JSON object.")
        output = gemini_explain(record) if args.provider == "gemini" else explain(record)
        print(json.dumps(output, indent=2))
        return 0
    except (OSError, sqlite3.Error, ValueError) as exc:
        # Keep filesystem contents, API response bodies, and credentials out of diagnostics.
        message = str(exc) if isinstance(exc, ExplanationError) else "Could not read or save data. Check paths, file format, and permissions."
        print(message, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
