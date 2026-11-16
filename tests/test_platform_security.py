"""Security controls: passwords, sessions, encryption at rest, audit tamper detection and HTTP headers."""
import unittest
from datetime import timedelta
from pathlib import Path

from cryptography.fernet import Fernet
from sqlalchemy import select, update

from claims_platform import audit
from claims_platform.db import utcnow
from claims_platform.demo import build_file
from claims_platform.models import AuditEntry, AuthSession, DownstreamRecord, Finding, User
from claims_platform.reporting import findings_csv_text
from claims_platform.scenarios import Api, approve_mapping, new_client, prepare_mapping, setup_team, upload, validate
from claims_platform.security import Cipher, hash_password, new_token, token_digest, verify_password
from claims_onboarding import synth

from _platform_env import PASSWORD, Platform


class PasswordAndTokenTests(unittest.TestCase):
    def test_hash_verifies_only_the_right_password(self):
        stored = hash_password("Correct-Horse-9")
        self.assertTrue(stored.startswith("scrypt$"))
        self.assertTrue(verify_password("Correct-Horse-9", stored))
        self.assertFalse(verify_password("correct-horse-9", stored))
        self.assertFalse(verify_password("anything", "not-a-hash"))

    def test_same_password_hashes_differently(self):
        self.assertNotEqual(hash_password("Correct-Horse-9"), hash_password("Correct-Horse-9"))

    def test_tokens_are_stored_only_as_digests(self):
        token, digest = new_token()
        self.assertEqual(token_digest(token), digest)
        self.assertNotIn(token, digest)
        self.assertGreaterEqual(len(token), 40)

    def test_cipher_round_trip_and_wrong_key(self):
        a, b = Cipher(Fernet.generate_key()), Cipher(Fernet.generate_key())
        token = a.encrypt(b"CLM1000001")
        self.assertNotIn(b"CLM1000001", token)
        self.assertEqual(a.decrypt(token), b"CLM1000001")
        with self.assertRaises(ValueError):
            b.decrypt(token)

    def test_key_rotation_keeps_old_data_readable(self):
        old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
        token = Cipher(old).encrypt(b"CLM1000001")
        both = Cipher(f"{new},{old}")
        self.assertEqual(both.decrypt(token), b"CLM1000001")
        rotated = both.rotate(token)
        self.assertEqual(Cipher(new).decrypt(rotated), b"CLM1000001")
        with self.assertRaises(ValueError):
            Cipher(old).decrypt(rotated)

    def test_csv_export_neutralises_spreadsheet_formulas(self):
        text = findings_csv_text([{"line": 2, "field": "f", "client_column": "c", "entered": "=HYPERLINK(1)",
                                   "rule": "r", "severity": "blocker", "message": "m"}])
        self.assertIn("'=HYPERLINK(1)", text)


class PlatformSecurityTests(unittest.TestCase):
    def setUp(self):
        self.p = Platform(export_batch_size=200)
        self.p.__enter__()
        self.api = Api(self.p.client)
        self.api.login("admin", PASSWORD)
        setup_team(self.api, PASSWORD)

    def tearDown(self):
        self.p.__exit__(None, None, None)

    def _client_with_run(self):
        c = new_client(self.api, "ana", "S-SEC", "Security test (synthetic)", ["priya"])
        raw, _ = build_file(rows=300, seed=5, breaks=[("provider_npi", "exactly 10 digits", 3)])
        sub = upload(self.api, "ana", c["id"], "sec.csv", raw)["submission"]
        m = prepare_mapping(self.api, "ana", sub["id"], synth.ANSWER_KEY)
        approve_mapping(self.api, "priya", m["id"])
        return c, raw, validate(self.api, "ana", sub["id"])

    def test_uploaded_files_and_finding_values_are_encrypted_at_rest(self):
        c, raw, run = self._client_with_run()
        stored = list(Path(self.p.settings.storage_dir).rglob("*.bin"))
        self.assertEqual(len(stored), 1)
        blob = stored[0].read_bytes()
        self.assertNotIn(b"CLM1000000", blob)
        self.assertNotIn(b"Rendering NPI", blob)
        with self.p.Session() as db:
            values = db.execute(select(Finding.entered_enc).where(Finding.run_id == run["id"])).scalars().all()
        self.assertEqual(len(values), 3)
        self.assertTrue(all(v.startswith(b"gAAAAA") for v in values))   # Fernet tokens, not plain values
        api_values = [f["entered"] for f in self.api.ok("GET", "ana", f"/api/runs/{run['id']}/findings")["items"]]
        self.assertTrue(all(len(v) == 9 and v.isdigit() for v in api_values))   # the API decrypts for users
        for token in values:
            self.assertFalse(any(v.encode() in token for v in api_values))

    def test_downstream_payloads_are_encrypted(self):
        c = new_client(self.api, "ana", "S-DS", "Downstream (synthetic)", ["priya"])
        raw, _ = build_file(rows=250, seed=6)
        sub = upload(self.api, "ana", c["id"], "ds.csv", raw)["submission"]
        approve_mapping(self.api, "priya", prepare_mapping(self.api, "ana", sub["id"], synth.ANSWER_KEY)["id"])
        validate(self.api, "ana", sub["id"])
        self.api.ok("POST", "priya", f"/api/clients/{c['id']}/golive", json={"approve": True, "comment": "ok"})
        self.api.ok("POST", "ana", f"/api/clients/{c['id']}/exports")
        with self.p.Session() as db:
            payloads = db.execute(select(DownstreamRecord.payload_enc)).scalars().all()
        self.assertEqual(len(payloads), 250)
        self.assertFalse(any(b"billed_amount" in x for x in payloads))

    def test_rotate_key_re_encrypts_files_and_values(self):
        from claims_platform.cli import rotate_key
        c, raw, run = self._client_with_run()
        old = self.p.settings.encryption_key
        new = Fernet.generate_key().decode()
        self.p.settings.encryption_key = f"{new},{old}"
        counts = rotate_key(self.p.Session, self.p.settings)
        self.assertEqual((counts["findings"], counts["files"]), (3, 1))
        only_new = Cipher(new)
        blob = next(Path(self.p.settings.storage_dir).rglob("*.bin")).read_bytes()
        self.assertEqual(only_new.decrypt(blob), raw)
        with self.p.Session() as db:
            for token in db.execute(select(Finding.entered_enc)).scalars():
                self.assertEqual(len(only_new.decrypt(token)), 9)

    def test_audit_tampering_is_detected(self):
        self._client_with_run()
        self.assertTrue(self.api.ok("GET", "admin", "/api/audit/verify")["ok"])
        with self.p.Session() as db:
            target = db.execute(select(AuditEntry).where(AuditEntry.action == "mapping.approved")).scalar_one()
            db.execute(update(AuditEntry).where(AuditEntry.id == target.id).values(actor="ana"))
            db.commit()
        result = self.api.ok("GET", "admin", "/api/audit/verify")
        self.assertFalse(result["ok"])
        self.assertEqual(result["first_bad_id"], target.id)

    def test_deleting_the_newest_audit_entries_is_detected(self):
        self._client_with_run()
        with self.p.Session() as db:
            last = db.execute(select(AuditEntry).order_by(AuditEntry.id.desc())).scalars().first()
            db.delete(last)
            db.commit()
        self.assertFalse(self.api.ok("GET", "admin", "/api/audit/verify")["ok"])

    def test_expired_session_is_refused(self):
        with self.p.Session() as db:
            db.execute(update(AuthSession).values(expires_at=utcnow() - timedelta(minutes=1)))
            db.commit()
        self.assertEqual(self.api.get("ana", "/api/auth/me").status_code, 401)

    def test_disabling_a_user_ends_their_sessions(self):
        self.api.ok("PATCH", "admin", f"/api/users/{self.api.user_ids['sam']}", json={"active": False})
        self.assertEqual(self.api.get("sam", "/api/auth/me").status_code, 401)
        self.assertEqual(self.api.login("sam", PASSWORD).status_code, 401)

    def test_unknown_and_wrong_password_look_the_same(self):
        a = self.p.client.post("/api/auth/login", json={"username": "nobody", "password": "x"})
        b = self.p.client.post("/api/auth/login", json={"username": "ana", "password": "x"})
        self.assertEqual((a.status_code, a.json()), (b.status_code, b.json()))

    def test_password_change_requires_current_password_and_signs_out(self):
        r = self.api.post("ana", "/api/auth/password", json={"current_password": "wrong", "new_password": "New-Pass-2026x"})
        self.assertEqual(r.status_code, 403)
        self.api.ok("POST", "ana", "/api/auth/password", json={"current_password": PASSWORD,
                                                               "new_password": "New-Pass-2026x"})
        self.assertEqual(self.api.get("ana", "/api/auth/me").status_code, 401)
        self.assertEqual(self.api.login("ana", "New-Pass-2026x").status_code, 200)

    def test_only_admins_manage_users_and_simulation(self):
        for user in ("ana", "priya", "birch.contact"):
            self.assertEqual(self.api.get(user, "/api/users").status_code, 403)
            self.assertEqual(self.api.put(user, "/api/admin/simulation", json={}).status_code, 403)
            self.assertEqual(self.api.get(user, "/api/audit/verify").status_code, 403)

    def test_security_headers(self):
        r = self.p.client.get("/api/health")
        self.assertEqual(r.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(r.headers["X-Frame-Options"], "DENY")
        self.assertEqual(r.headers["Cache-Control"], "no-store")
        self.assertIn("frame-ancestors 'none'", r.headers["Content-Security-Policy"])

    def test_upload_filename_is_sanitised(self):
        c = new_client(self.api, "ana", "S-NAME", "Names (synthetic)", [])
        raw, _ = build_file(rows=10, seed=1)
        sub = upload(self.api, "ana", c["id"], "../../etc/<passwd>.csv", raw)["submission"]
        self.assertEqual(sub["filename"], "_passwd_.csv")

    def test_client_contacts_never_see_draft_letters(self):
        c, raw, run = self._client_with_run()
        contact = self.api.ok("POST", "admin", "/api/users", json={
            "username": "sec.contact", "display_name": "Sec contact", "role": "client_contact", "password": PASSWORD})
        self.api.ok("POST", "admin", f"/api/clients/{c['id']}/access", json={"user_id": contact["id"]})
        self.api.login("sec.contact", PASSWORD)
        letter = self.api.ok("POST", "ana", f"/api/clients/{c['id']}/communications", json={"kind": "issue_letter"})
        self.assertEqual(self.api.get("sec.contact", f"/api/communications/{letter['id']}").status_code, 404)
        self.assertEqual(self.api.ok("GET", "sec.contact", f"/api/clients/{c['id']}/communications"), [])
        run_view = self.api.ok("GET", "sec.contact", f"/api/runs/{run['id']}")
        self.assertNotIn("facts", run_view)   # internal mapping and correction details stay internal

    def test_admin_cannot_remove_own_admin_role(self):
        r = self.api.patch("admin", f"/api/users/{self.api.user_ids['admin']}", json={"role": "approver"})
        self.assertEqual(r.status_code, 409)
        with self.p.Session() as db:
            self.assertEqual(db.execute(select(User.role).where(User.username == "admin")).scalar(), "admin")


if __name__ == "__main__":
    unittest.main()
