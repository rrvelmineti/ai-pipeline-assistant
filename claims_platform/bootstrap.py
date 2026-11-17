"""First start on an empty database: create the first administrator, or load the synthetic demo.

Hosts without a shell (such as Render's free tier) cannot run `cli create-admin` or `cli seed-demo`,
so the same work can happen at start-up, driven by CLAIMS_SEED_DEMO, CLAIMS_DEMO_PASSWORD and
CLAIMS_ADMIN_PASSWORD. It runs only when the database has no users, so a restart changes nothing.
"""
import threading
from dataclasses import replace

from sqlalchemy import select

from .db import Base, utcnow
from .models import Client, Setting, User
from .security import check_password_strength, hash_password

STATUS_KEY = "demo_seed"
DEMO_CLIENTS = {"A-ASTER", "B-BIRCH", "C-CEDAR", "C2-CEDAR-WEST", "D-DOGWOOD", "E-ELM", "F-FIR", "P-PERF"}


def ensure_admin(Session, username, password, display_name="Administrator"):
    check_password_strength(password)
    from . import audit
    with Session() as db:
        if db.execute(select(User).where(User.username == username)).scalar_one_or_none():
            return False
        u = User(username=username, display_name=display_name, role="admin", password_hash=hash_password(password))
        db.add(u)
        db.flush()
        audit.record(db, None, "user.created", entity="user", entity_id=u.id,
                     detail={"username": username, "role": "admin", "via": "bootstrap"})
        db.commit()
        return True


def _set_status(Session, value):
    with Session() as db:
        row = db.get(Setting, STATUS_KEY)
        if row is None:
            db.add(Setting(key=STATUS_KEY, value=value))
        else:
            row.value = value
        db.commit()


def demo_status(Session):
    with Session() as db:
        row = db.get(Setting, STATUS_KEY)
        return row.value.get("status") if row is not None else None


def seed_demo(settings, password, performance=False):
    """Load scenarios A–F through the API into the configured database. Returns the scenario results."""
    from fastapi.testclient import TestClient

    from .app import create_app
    from .scenarios import run_all
    # The seeding instance needs fault injection for scenario E; the public instance keeps its own setting.
    app = create_app(replace(settings, simulation_enabled=True, seed_demo=False, admin_password=""))
    try:
        with TestClient(app) as client:
            ensure_admin(app.state.Session, "admin", password)
            results, _ = run_all(client, password, password, include_performance=performance)
    finally:
        app.state.engine.dispose()
    return results


def _seed_in_background(settings, Session):
    _set_status(Session, {"status": "running", "started": utcnow().isoformat(timespec="seconds")})
    print("claims_platform: loading the synthetic demo (scenarios A-F)...", flush=True)
    try:
        results = seed_demo(settings, settings.demo_password)
        _set_status(Session, {"status": "ready", "finished": utcnow().isoformat(timespec="seconds"),
                              "checks": f"{results['checks_passed']} of {results['checks_total']}"})
        print(f"claims_platform: demo ready, {results['checks_passed']} of {results['checks_total']} checks passed.",
              flush=True)
    except Exception as exc:  # reported in the log and on /api/health; the platform itself keeps running
        _set_status(Session, {"status": "failed", "error": f"{type(exc).__name__}: {exc}"[:300]})
        print(f"claims_platform: demo seeding failed: {type(exc).__name__}: {exc}", flush=True)


def _only_an_unfinished_demo(Session):
    """True when an earlier demo load stopped part-way (failed, or the process stopped while it ran) and the
    database holds nothing but demo users and demo clients, so it is safe to start the demo again."""
    from .scenarios import TEAM
    if demo_status(Session) not in ("failed", "running"):
        return False
    with Session() as db:
        users = set(db.execute(select(User.username)).scalars())
        clients = set(db.execute(select(Client.code)).scalars())
    return users <= {"admin", *(u for u, _, _ in TEAM)} and clients <= DEMO_CLIENTS


def bootstrap(settings, Session, engine=None):
    """Returns the seeding thread when one was started (tests join it), otherwise None.

    Runs at start-up, when nothing else in this single-process app can be loading the demo.
    """
    with Session() as db:
        has_users = db.execute(select(User.id).limit(1)).first() is not None
    if has_users and settings.seed_demo and engine is not None and _only_an_unfinished_demo(Session):
        print("claims_platform: the last demo load did not finish; clearing the demo data and loading it again.",
              flush=True)
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        has_users = False
    if has_users:
        return None
    if settings.seed_demo:
        if not settings.demo_password:
            print("claims_platform: CLAIMS_SEED_DEMO is set but CLAIMS_DEMO_PASSWORD is empty; not seeding.", flush=True)
            return None
        check_password_strength(settings.demo_password)
        thread = threading.Thread(target=_seed_in_background, args=(settings, Session), name="demo-seed", daemon=True)
        thread.start()
        return thread
    if settings.admin_password:
        ensure_admin(Session, "admin", settings.admin_password)
        print("claims_platform: created the administrator 'admin' from CLAIMS_ADMIN_PASSWORD.", flush=True)
    return None
