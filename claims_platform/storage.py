"""Uploaded files, encrypted at rest, stored by client and content hash: on disk or in the database."""
import hashlib
import os
from pathlib import Path

from sqlalchemy.exc import IntegrityError


def _key(client_id, raw):
    sha = hashlib.sha256(raw).hexdigest()
    return sha, f"client-{int(client_id)}/{sha}.bin"


class FileStore:
    """Encrypted files in a directory. Use where the disk survives restarts."""

    def __init__(self, root, cipher):
        self.root = Path(root)
        self.cipher = cipher

    def put(self, client_id, raw):
        sha, key = _key(client_id, raw)
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(self.cipher.encrypt(raw))
        os.replace(tmp, path)   # atomic: a crash never leaves a half-written file under the final name
        return sha, key

    def get(self, key):
        path = (self.root / key).resolve()
        if self.root.resolve() not in path.parents:
            raise ValueError("Invalid storage key.")
        return self.cipher.decrypt(path.read_bytes())


class DatabaseFileStore:
    """Encrypted files in the database, for hosts whose local disk is wiped on restart."""

    def __init__(self, Session, cipher):
        self.Session = Session
        self.cipher = cipher

    def put(self, client_id, raw):
        from .models import StoredFile
        sha, key = _key(client_id, raw)
        with self.Session() as db:
            if db.get(StoredFile, key) is None:
                db.add(StoredFile(key=key, client_id=client_id, data=self.cipher.encrypt(raw)))
                try:
                    db.commit()
                except IntegrityError:   # the same file stored by a parallel request: already there
                    db.rollback()
        return sha, key

    def get(self, key):
        from .models import StoredFile
        with self.Session() as db:
            row = db.get(StoredFile, key)
            if row is None:
                raise ValueError("The stored file is missing.")
            return self.cipher.decrypt(row.data)


def make_store(settings, Session, cipher):
    if settings.file_store == "database":
        return DatabaseFileStore(Session, cipher)
    if settings.file_store != "disk":
        raise ValueError("CLAIMS_FILE_STORE must be 'disk' or 'database'.")
    return FileStore(settings.storage_dir, cipher)
