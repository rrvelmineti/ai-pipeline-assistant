"""Command line for operators.

  python -m claims_platform.cli init                    create the database tables
  python -m claims_platform.cli create-admin admin      create an administrator (password from CLAIMS_ADMIN_PASSWORD or a prompt)
  python -m claims_platform.cli seed-demo               load the synthetic scenarios A–F into an empty database
  python -m claims_platform.cli recover                 mark runs and exports left mid-flight for a safe retry
  python -m claims_platform.cli verify-audit            recompute the audit hash chain
  python -m claims_platform.cli rotate-key              re-encrypt everything under the first key in CLAIMS_ENCRYPTION_KEY
  python -m claims_platform.cli serve                   run the web app on http://127.0.0.1:8000
"""
import argparse
import getpass
import json
import os
import secrets
import sys

from sqlalchemy import func, select

from .bootstrap import ensure_admin, seed_demo
from .config import Settings
from .db import Base, make_engine, make_session_factory
from .models import User


def _session(settings):
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    return engine, make_session_factory(engine)


def rotate_key(Session, settings):
    """Re-encrypt stored files and values under the newest key. Safe to run twice."""
    from pathlib import Path

    from .models import Communication, DownstreamRecord, Finding, StoredFile
    from .security import load_cipher
    cipher = load_cipher(settings)
    counts = {}
    with Session() as db:
        for model, column in ((Finding, "entered_enc"), (Communication, "body_enc"),
                              (DownstreamRecord, "payload_enc"), (StoredFile, "data")):
            n = 0
            for row in db.execute(select(model)).scalars():
                setattr(row, column, cipher.rotate(getattr(row, column)))
                n += 1
            counts[model.__tablename__] = n
        db.commit()
    files = 0
    for path in Path(settings.storage_dir).rglob("*.bin"):
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(cipher.rotate(path.read_bytes()))
        os.replace(tmp, path)
        files += 1
    counts["files"] = files
    return counts


def _password(env_name, prompt):
    value = os.environ.get(env_name)
    if value:
        return value
    if sys.stdin.isatty():
        return getpass.getpass(prompt)
    raise SystemExit(f"Set {env_name} or run interactively.")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="claims_platform", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    p = sub.add_parser("create-admin")
    p.add_argument("username")
    p = sub.add_parser("seed-demo")
    p.add_argument("--performance", action="store_true", help="also load the 100,000-row file")
    sub.add_parser("recover")
    sub.add_parser("verify-audit")
    sub.add_parser("rotate-key")
    p = sub.add_parser("serve")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    settings = Settings()

    if args.command == "serve":
        import uvicorn
        uvicorn.run("claims_platform.app:create_app", factory=True, host=args.host, port=args.port, workers=1)
        return
    engine, Session = _session(settings)
    try:
        if args.command == "init":
            print("Tables created.")
        elif args.command == "create-admin":
            created = ensure_admin(Session, args.username, _password("CLAIMS_ADMIN_PASSWORD", "Admin password: "))
            print("Administrator created." if created else "That user already exists; nothing changed.")
        elif args.command == "recover":
            from .processing import recover_interrupted
            with Session() as db:
                print(json.dumps(recover_interrupted(db)))
                db.commit()
        elif args.command == "verify-audit":
            from .audit import verify
            with Session() as db:
                result = verify(db)
            print(json.dumps(result))
            if not result["ok"]:
                raise SystemExit(1)
        elif args.command == "rotate-key":
            print(json.dumps(rotate_key(Session, settings)))
        elif args.command == "seed-demo":
            with Session() as db:
                if db.execute(select(func.count(User.id))).scalar():
                    raise SystemExit("seed-demo needs an empty database. Point CLAIMS_DATABASE_URL at a new one.")
            password = os.environ.get("CLAIMS_DEMO_PASSWORD") or ("Demo-" + secrets.token_urlsafe(9))
            from .scenarios import TEAM
            results = seed_demo(settings, password, performance=args.performance)
            print(f"Loaded scenarios A–F: {results['checks_passed']} of {results['checks_total']} checks passed.")
            print("Demo users (synthetic data only): admin, " + ", ".join(u for u, _, _ in TEAM))
            if not os.environ.get("CLAIMS_DEMO_PASSWORD"):
                print(f"Password for every demo user: {password}  (shown once; set CLAIMS_DEMO_PASSWORD to choose it)")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
