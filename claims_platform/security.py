"""Passwords, session tokens and encryption at rest. Standard library scrypt plus Fernet."""
import base64
import hashlib
import hmac
import secrets
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 14, 8, 1
MIN_PASSWORD_LENGTH = 12


def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32)
    return "scrypt${}${}${}${}${}".format(SCRYPT_N, SCRYPT_R, SCRYPT_P,
                                          base64.b64encode(salt).decode(), base64.b64encode(digest).decode())


def verify_password(password, stored):
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        got = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p),
                             dklen=32)
        return hmac.compare_digest(got, base64.b64decode(digest))
    except (ValueError, TypeError):
        return False


# Spend the same time on unknown usernames as on real ones, so response time does not reveal accounts.
_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def burn_password_check(password):
    verify_password(password, _DUMMY_HASH)


def check_password_strength(password):
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Passwords need at least {MIN_PASSWORD_LENGTH} characters.")
    if password.isalpha() or password.isdigit():
        raise ValueError("Use a mix of letters and digits or symbols.")


def new_token():
    token = secrets.token_urlsafe(32)
    return token, token_digest(token)


def token_digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


class Cipher:
    """Fernet (AES-128-CBC with HMAC-SHA256) for uploaded files and sensitive values.

    The key may be a comma-separated list: the first key encrypts, every key can decrypt. That is how a
    key is rotated (see `cli rotate-key` and docs/platform/runbooks.md).
    """

    def __init__(self, key):
        raw = key.decode() if isinstance(key, bytes) else key
        keys = [k.strip() for k in raw.split(",") if k.strip()]
        self._fernet = MultiFernet([Fernet(k.encode()) for k in keys])

    def rotate(self, token):
        """Re-encrypt a token under the first (newest) key."""
        try:
            return self._fernet.rotate(token)
        except InvalidToken:
            raise ValueError("Stored data could not be decrypted with any configured key.") from None

    def encrypt(self, data):
        return self._fernet.encrypt(data if isinstance(data, bytes) else str(data).encode())

    def decrypt(self, token):
        try:
            return self._fernet.decrypt(token)
        except InvalidToken:
            raise ValueError("Stored data could not be decrypted with the configured key.") from None

    def decrypt_text(self, token):
        return self.decrypt(token).decode()


def load_cipher(settings):
    """Use CLAIMS_ENCRYPTION_KEY. In development only, create and reuse a local key file instead."""
    if settings.encryption_key:
        return Cipher(settings.encryption_key)
    if not settings.allow_dev_key:
        raise RuntimeError("CLAIMS_ENCRYPTION_KEY is required when CLAIMS_ENV is not 'development'.")
    path = Path(settings.storage_dir) / "dev-encryption.key"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(Fernet.generate_key())
    return Cipher(path.read_bytes().strip())
