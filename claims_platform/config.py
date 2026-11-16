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
