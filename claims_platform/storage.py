"""Uploaded files, encrypted at rest, stored by client and content hash."""
import hashlib
import os
from pathlib import Path


class FileStore:
    def __init__(self, root, cipher):
        self.root = Path(root)
        self.cipher = cipher

    def put(self, client_id, raw):
        sha = hashlib.sha256(raw).hexdigest()
        key = f"client-{int(client_id)}/{sha}.bin"
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
