"""Encrypted-at-rest secret storage.

Secrets are encrypted with Fernet (AES128-CBC + HMAC). The master key is read
from SETTINGS_ENCRYPTION_KEY (any strong passphrase or a valid Fernet key).
When unset, a key file is generated next to the SQLite database for local
development only; always set SETTINGS_ENCRYPTION_KEY in production.
"""
import base64
import hashlib
import os
from pathlib import Path

try:
    from cryptography.fernet import Fernet, InvalidToken
    _CRYPTO_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    Fernet = None
    InvalidToken = Exception
    _CRYPTO_AVAILABLE = False

_KEY_FILE_NAME = ".settings_key"


def crypto_available() -> bool:
    return _CRYPTO_AVAILABLE


def _derive_key(raw: str) -> bytes:
    raw = raw.strip()
    try:
        Fernet(raw.encode())
        return raw.encode()
    except Exception:
        digest = hashlib.sha256(raw.encode()).digest()
        return base64.urlsafe_b64encode(digest)


def _default_key_path() -> str:
    db_url = os.getenv("DATABASE_URL", "")
    if db_url.startswith("sqlite:///"):
        db_path = db_url.replace("sqlite:///", "")
    else:
        db_path = os.path.join("data", "bot.db")
    return str(Path(db_path).expanduser().resolve().parent / _KEY_FILE_NAME)


class SecretBox:
    def __init__(self, key: str | None = None, key_path: str | None = None):
        self.key_path = key_path or _default_key_path()
        self._fernet = None
        if not _CRYPTO_AVAILABLE:
            return
        raw = key if key is not None else os.getenv("SETTINGS_ENCRYPTION_KEY", "")
        if raw:
            self._fernet = Fernet(_derive_key(raw))
            return
        # Local-development fallback: persist a generated key next to the DB.
        try:
            p = Path(self.key_path)
            if p.exists():
                self._fernet = Fernet(p.read_bytes().strip())
            else:
                p.parent.mkdir(parents=True, exist_ok=True)
                key_bytes = Fernet.generate_key()
                p.write_bytes(key_bytes)
                try:
                    os.chmod(p, 0o600)
                except Exception:
                    pass
                self._fernet = Fernet(key_bytes)
        except Exception:
            self._fernet = None

    @property
    def available(self) -> bool:
        return self._fernet is not None

    def encrypt(self, value: str) -> str:
        if not self.available:
            raise RuntimeError("encryption unavailable; set SETTINGS_ENCRYPTION_KEY")
        return self._fernet.encrypt(str(value).encode()).decode()

    def decrypt(self, token: str) -> str:
        if not self.available:
            raise RuntimeError("encryption unavailable; set SETTINGS_ENCRYPTION_KEY")
        try:
            return self._fernet.decrypt(str(token).encode()).decode()
        except InvalidToken as exc:
            raise ValueError("could not decrypt secret (wrong key?)") from exc
