"""Settings read from environment variables. Defaults suit a local, single-process pilot."""
import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _int(name, default):
    value = os.environ.get(name)
    return int(value) if value not in (None, "") else default


@dataclass
class Settings:
    database_url: str = field(default_factory=lambda: os.environ.get(
        "CLAIMS_DATABASE_URL", f"sqlite:///{(ROOT / 'local_data' / 'claims_platform.db').as_posix()}"))
    storage_dir: Path = field(default_factory=lambda: Path(os.environ.get(
        "CLAIMS_STORAGE_DIR", ROOT / "local_data" / "platform_files")))
    # Fernet key (urlsafe base64, 32 bytes). Required outside development; see docs/platform/configuration.md.
    encryption_key: str = field(default_factory=lambda: os.environ.get("CLAIMS_ENCRYPTION_KEY", ""))
    session_hours: int = field(default_factory=lambda: _int("CLAIMS_SESSION_HOURS", 8))
    lockout_attempts: int = field(default_factory=lambda: _int("CLAIMS_LOCKOUT_ATTEMPTS", 5))
    lockout_minutes: int = field(default_factory=lambda: _int("CLAIMS_LOCKOUT_MINUTES", 15))
    export_batch_size: int = field(default_factory=lambda: _int("CLAIMS_EXPORT_BATCH_SIZE", 500))
    export_batch_attempts: int = field(default_factory=lambda: _int("CLAIMS_EXPORT_BATCH_ATTEMPTS", 3))
    # Fault injection for the operational-failure scenarios. Turn off in any shared environment.
    simulation_enabled: bool = field(default_factory=lambda: os.environ.get("CLAIMS_SIMULATION", "1") == "1")
    web_dist: Path = field(default_factory=lambda: Path(os.environ.get(
        "CLAIMS_WEB_DIST", ROOT / "claims_platform_web" / "dist")))
    # Development only: create a key file next to the database when no key is configured.
    allow_dev_key: bool = field(default_factory=lambda: os.environ.get("CLAIMS_ENV", "development") == "development")
    # "disk" keeps encrypted uploads in storage_dir; "database" keeps them in the database, for hosts whose
    # disk is wiped on restart (such as Render's free tier).
    file_store: str = field(default_factory=lambda: os.environ.get("CLAIMS_FILE_STORE", "disk"))
    # On an empty database at start-up: load the synthetic demo (scenarios A–F) in the background, using
    # demo_password for every demo user; or, if not seeding, create the user 'admin' with admin_password.
    seed_demo: bool = field(default_factory=lambda: os.environ.get("CLAIMS_SEED_DEMO", "0") == "1")
    demo_password: str = field(default_factory=lambda: os.environ.get("CLAIMS_DEMO_PASSWORD", ""))
    admin_password: str = field(default_factory=lambda: os.environ.get("CLAIMS_ADMIN_PASSWORD", ""))


def normalise_database_url(url):
    """Hosts such as Render hand out postgres:// or postgresql:// URLs; SQLAlchemy needs the driver named."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url
