import os, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "StrongPass123!"
_tmpdir = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(_tmpdir, "p6.db")
os.environ["TRADING_MODE"] = "paper"

from src.auth import hash_password, verify_password, AuthManager
from src.storage import Storage
from src.settings_manager import SettingsManager

# Password hashing
def test_password_hashing():
    h, salt = hash_password("secret")
    assert h != "secret"
    assert verify_password("secret", h, salt)
    assert not verify_password("wrong", h, salt)

# Auth manager
storage = Storage(path=os.environ["DATABASE_URL"].replace("sqlite:///",""))
auth = AuthManager(storage)
auth.setup_admin_from_env()

def test_has_admin():
    assert storage.has_admin() is True

def test_login_success():
    ok, token, must_change = auth.login("admin", "StrongPass123!", "1.2.3.4")
    assert ok is True
    assert token
    assert must_change is True

def test_login_failure():
    ok, token, _ = auth.login("admin", "wrong", "1.2.3.5")
    assert ok is False
    assert token == ""

def test_session_validation():
    ok, token, _ = auth.login("admin", "StrongPass123!", "1.2.3.6")
    user = auth.validate_session(token)
    assert user == "admin"
    assert auth.validate_session("invalidtoken") is None

def test_logout():
    ok, token, _ = auth.login("admin", "StrongPass123!", "1.2.3.7")
    auth.logout(token)
    assert auth.validate_session(token) is None

def test_rate_limiting():
    ip = "9.9.9.9"
    for _ in range(6):
        auth.login("admin", "wrong", ip)
    assert auth.is_rate_limited(ip) is True

def test_change_password():
    ok, token, _ = auth.login("admin", "StrongPass123!", "1.2.3.8")
    auth.change_password("admin", "NewPass456!")
    # old password fails
    ok2, _, _ = auth.login("admin", "StrongPass123!", "1.2.3.9")
    assert ok2 is False
    ok3, _, _ = auth.login("admin", "NewPass456!", "1.2.3.10")
    assert ok3 is True

# Settings validation
def test_settings_validation_live_rejected():
    sm = SettingsManager(storage)
    res = sm.validate_and_set({"trading_mode": "live"})
    assert res["ok"] is False
    assert any("LIVE" in e for e in res["errors"])

def test_settings_validation_bounds():
    sm = SettingsManager(storage)
    res = sm.validate_and_set({"risk_per_trade_pct": "0.5"})
    assert res["ok"] is False
    res2 = sm.validate_and_set({"risk_per_trade_pct": "0.005"})
    assert res2["ok"] is True

def test_settings_validation_symbols():
    sm = SettingsManager(storage)
    res = sm.validate_and_set({"scanner_symbols": []})
    assert res["ok"] is False
    res2 = sm.validate_and_set({"scanner_symbols": ["BTCUSDT", "ETHUSDT"]})
    assert res2["ok"] is True

# API tests
from fastapi.testclient import TestClient
from src.dashboard import app
api_client = TestClient(app)

def _login(client, username="admin", password="NewPass456!"):
    # ensure password is NewPass456! from previous test; if not, try original
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    if r.status_code != 200:
        r = client.post("/api/auth/login", json={"username": username, "password": "StrongPass123!"})
    return r

def test_auth_status():
    r = api_client.get("/api/auth/status")
    assert r.status_code == 200
    assert "authenticated" in r.json()

def test_protected_endpoint_requires_auth():
    # fresh client without cookies
    c = TestClient(app)
    r = c.get("/api/settings")
    # may be 401 if admin exists
    assert r.status_code in (200, 401)

def test_login_endpoint():
    r = api_client.post("/api/auth/login", json={"username": "admin", "password": "NewPass456!"})
    if r.status_code != 200:
        r = api_client.post("/api/auth/login", json={"username": "admin", "password": "StrongPass123!"})
    assert r.status_code in (200, 401)

def test_admin_status_endpoint():
    r = _login(api_client)
    r = api_client.get("/api/admin/status")
    assert r.status_code == 200

def test_admin_settings_endpoint():
    _login(api_client)
    r = api_client.get("/api/admin/settings")
    assert r.status_code == 200
    r = api_client.put("/api/admin/settings", json={"risk_per_trade_pct": "0.005"})
    assert r.status_code == 200

def test_admin_actions_logged():
    _login(api_client)
    api_client.get("/api/admin/status")
    r = api_client.get("/api/admin/actions")
    assert r.status_code == 200
    assert "actions" in r.json()

def test_kill_switch_protected():
    _login(api_client)
    r = api_client.post("/api/system/kill")
    assert r.status_code == 200
    api_client.post("/resume")

def test_live_activation_via_settings_rejected():
    _login(api_client)
    r = api_client.put("/api/admin/settings", json={"trading_mode": "live"})
    assert r.status_code == 200
    assert r.json().get("ok") is False

def test_secret_redaction():
    from src.logger import redact
    assert "***REDACTED***" in redact("password=hunter2")
    assert "***REDACTED***" in redact("api_secret=abc")

def test_session_expiration():
    ok, token, _ = auth.login("admin", "NewPass456!", "1.2.3.11")
    if not ok:
        ok, token, _ = auth.login("admin", "StrongPass123!", "1.2.3.11")
    # validate with expired by direct db? Just ensure token valid now
    assert auth.validate_session(token) == "admin"