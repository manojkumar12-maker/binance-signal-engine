"""Lightweight authentication for the personal dashboard."""
import os
import secrets
import hashlib
import time
from .storage import Storage


def hash_password(password: str, salt: str | None = None):
    if salt is None:
        salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000)
    return h.hex(), salt


def verify_password(password: str, stored_hash: str, salt: str) -> bool:
    h, _ = hash_password(password, salt)
    return secrets.compare_digest(h, stored_hash)


class AuthManager:
    def __init__(self, storage: Storage):
        self.storage = storage
        self._attempts = {}  # ip -> [count, lock_until]
        self.session_ttl = int(os.getenv("SESSION_TTL_SECONDS", "3600"))
        self.max_attempts = int(os.getenv("MAX_LOGIN_ATTEMPTS", "5"))
        self.lockout_seconds = int(os.getenv("LOCKOUT_SECONDS", "300"))

    def setup_admin_from_env(self):
        username = os.getenv("ADMIN_USERNAME", "")
        password = os.getenv("ADMIN_PASSWORD", "")
        if not username or not password:
            return False
        if self.storage.has_admin():
            return False
        h, salt = hash_password(password)
        self.storage.create_user(username, h, salt, must_change_password=True)
        return True

    def is_rate_limited(self, ip: str) -> bool:
        now = time.time()
        info = self._attempts.get(ip)
        if not info:
            return False
        count, lock_until = info
        if lock_until and now < lock_until:
            return True
        if lock_until and now >= lock_until:
            self._attempts.pop(ip, None)
        return False

    def record_failure(self, ip: str):
        now = time.time()
        info = self._attempts.get(ip, [0, 0])
        count = info[0] + 1
        lock_until = 0
        if count >= self.max_attempts:
            lock_until = now + self.lockout_seconds
        self._attempts[ip] = [count, lock_until]

    def clear_failures(self, ip: str):
        self._attempts.pop(ip, None)

    def login(self, username: str, password: str, ip: str = "") -> tuple[bool, str, bool]:
        if self.is_rate_limited(ip):
            return False, "", False
        user = self.storage.get_user(username)
        if not user:
            self.record_failure(ip)
            return False, "", False
        if not verify_password(password, user["password_hash"], user["salt"]):
            self.record_failure(ip)
            return False, "", False
        self.clear_failures(ip)
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        expires = time.time() + self.session_ttl
        self.storage.create_session(token_hash, username, expires)
        return True, token, bool(user["must_change_password"])

    def validate_session(self, token: str | None) -> str | None:
        if not token:
            return None
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        sess = self.storage.get_session(token_hash)
        if not sess or sess["revoked"]:
            return None
        if sess["expires_at"] < time.time():
            self.storage.revoke_session(token_hash)
            return None
        return sess["username"]

    def logout(self, token: str | None):
        if not token:
            return
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        self.storage.revoke_session(token_hash)

    def change_password(self, username: str, new_password: str):
        h, salt = hash_password(new_password)
        self.storage.create_user(username, h, salt, must_change_password=False)
        self.storage.revoke_user_sessions(username)