"""Hosting support: database file store, host-style database URLs and keys, and first-start bootstrap."""
import base64
import os
import unittest
from pathlib import Path

from sqlalchemy import func, select

from claims_onboarding import synth
from claims_platform.config import normalise_database_url
from claims_platform.demo import build_file
from claims_platform.models import StoredFile, User
from claims_platform.scenarios import Api, approve_mapping, new_client, prepare_mapping, setup_team, upload, validate
from claims_platform.security import Cipher

from _platform_env import PASSWORD, Platform


class HostSettingsTests(unittest.TestCase):
    def test_host_database_urls_get_the_psycopg_driver(self):
        self.assertEqual(normalise_database_url("postgres://u:p@h:5432/d"), "postgresql+psycopg://u:p@h:5432/d")
        self.assertEqual(normalise_database_url("postgresql://u:p@h/d"), "postgresql+psycopg://u:p@h/d")
        self.assertEqual(normalise_database_url("postgresql+psycopg://u@h/d"), "postgresql+psycopg://u@h/d")
        self.assertEqual(normalise_database_url("sqlite:///x.db"), "sqlite:///x.db")

    def test_a_generated_secret_works_as_the_encryption_key(self):
        generated = base64.b64encode(os.urandom(32)).decode()   # the shape a hosting platform generates
        a, b = Cipher(generated), Cipher(generated)
        self.assertEqual(b.decrypt(a.encrypt(b"CLM1000001")), b"CLM1000001")
        long_phrase = "x" * 40
        self.assertEqual(Cipher(long_phrase).decrypt(Cipher(long_phrase).encrypt(b"v")), b"v")
        with self.assertRaises(ValueError):
            Cipher("too-short")


class DatabaseFileStoreTests(unittest.TestCase):
    def test_uploads_live_in_the_database_not_on_disk(self):
        with Platform(file_store="database") as p:
            api = Api(p.client)
            api.login("admin", PASSWORD)
            setup_team(api, PASSWORD)
            c = new_client(api, "ana", "DB-STORE", "Database store (synthetic)", ["priya"])
            raw, _ = build_file(rows=260, seed=3, breaks=[("provider_npi", "exactly 10 digits", 2)])
            sub = upload(api, "ana", c["id"], "db.csv", raw)["submission"]
            approve_mapping(api, "priya", prepare_mapping(api, "ana", sub["id"], synth.ANSWER_KEY)["id"])
            run = validate(api, "ana", sub["id"])
            self.assertEqual((run["status"], run["blockers"]), ("completed", 2))
            self.assertEqual(list(Path(p.settings.storage_dir).rglob("*.bin")), [])
            with p.Session() as db:
                blob = db.execute(select(StoredFile.data)).scalar_one()
            self.assertNotIn(b"Clm_Nbr", blob)
            from claims_platform.cli import rotate_key
            from cryptography.fernet import Fernet
            new = Fernet.generate_key().decode()
            p.settings.encryption_key = f"{new},{p.settings.encryption_key}"
            self.assertEqual(rotate_key(p.Session, p.settings)["stored_files"], 1)
            with p.Session() as db:
                self.assertEqual(Cipher(new).decrypt(db.execute(select(StoredFile.data)).scalar_one()), raw)


class BootstrapTests(unittest.TestCase):
    def test_admin_password_creates_the_first_administrator_once(self):
        with Platform(create_admin=False, admin_password="First-Admin-Pass-1") as p:
            self.assertEqual(p.client.post("/api/auth/login", json={"username": "admin",
                                                                    "password": "First-Admin-Pass-1"}).status_code, 200)
            with p.Session() as db:
                self.assertEqual(db.execute(select(func.count(User.id))).scalar(), 1)

    def test_first_start_loads_the_demo_in_the_background(self):
        with Platform(create_admin=False, seed_demo=True, demo_password=PASSWORD, file_store="database") as p:
            self.assertTrue(p.client.get("/api/health").status_code == 200)   # serving while the demo loads
            p.app.state.seed_thread.join(timeout=300)
            health = p.client.get("/api/health").json()
            self.assertEqual(health["demo"], "ready")
            api = Api(p.client)
            self.assertEqual(api.login("priya", PASSWORD).status_code, 200)
            codes = sorted(c["code"] for c in api.ok("GET", "priya", "/api/clients"))
            self.assertEqual(codes, ["A-ASTER", "B-BIRCH", "C-CEDAR", "C2-CEDAR-WEST", "D-DOGWOOD", "E-ELM", "F-FIR"])
            # Fault injection stays off in the public instance even though the seeding instance used it.
            api.login("admin", PASSWORD)
            self.assertEqual(api.put("admin", "/api/admin/simulation", json={}).status_code, 200
                             if p.settings.simulation_enabled else 404)


if __name__ == "__main__":
    unittest.main()
