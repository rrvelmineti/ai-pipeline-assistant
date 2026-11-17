"""A throwaway platform instance for tests: temporary SQLite (or CLAIMS_TEST_DATABASE_URL) and a fresh key."""
import os
import tempfile
from pathlib import Path

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from claims_platform.app import create_app
from claims_platform.bootstrap import ensure_admin
from claims_platform.config import Settings
from claims_platform.db import Base

PASSWORD = "Synthetic-Pass-2026"


class Platform:
    """Use as a context manager. Exposes .client (TestClient), .app, .Session and .settings."""

    def __init__(self, create_admin=True, **overrides):
        self.create_admin = create_admin
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        url = os.environ.get("CLAIMS_TEST_DATABASE_URL") or f"sqlite:///{Path(self.temp.name).as_posix()}/platform.db"
        self.settings = Settings(database_url=url, storage_dir=os.path.join(self.temp.name, "files"),
                                 encryption_key=Fernet.generate_key().decode(), web_dist=self.temp.name,
                                 **overrides)
        self.app = create_app(self.settings)
        self.Session = self.app.state.Session

    def __enter__(self):
        if self.settings.database_url.startswith("postgresql"):
            Base.metadata.drop_all(self.app.state.engine)   # each test starts from an empty shared database
        self.client = TestClient(self.app)
        self.client.__enter__()
        if self.create_admin:
            ensure_admin(self.Session, "admin", PASSWORD)
        return self

    def __exit__(self, *exc):
        self.client.__exit__(*exc)
        self.app.state.engine.dispose()
        self.temp.cleanup()
        return False
