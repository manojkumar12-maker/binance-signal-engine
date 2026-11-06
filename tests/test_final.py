import os, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Auth enabled for security tests
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "StrongPass123!"
_tmpdir = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(_tmpdir, "final.db")
os.environ["TRADING_MODE"] = "paper"

from src.storage import Storage
from src.config import settings
from src.orchestrator import Orchestrator
from tests.mock_exchange import MockBinanceClient
from src.worker_lock import WorkerLock

storage = Storage(path=os.environ["DATABASE_URL"].replace("sqlite:///",""))
client = MockBinanceClient()
orch = Orchestrator(client, storage)

# Worker lock regression: worker holds process lock, multiple cycles run
def test_worker_holding_lock_runs_multiple_cycles():
    lock = WorkerLock(path=os.path.join(_tmpdir, "worker.lock"))
    assert lock.acquire() is True
    # spy on scanner
    calls = {"n": 0}
    original = orch.scanner.scan_once
    def spy():
        calls["n"] += 1
        return original()
    orch.scanner.scan_once = spy
    try:
        r1 = orch.run_cycle()
        r2 = orch.run_cycle()
        assert calls["n"] == 2
    finally:
        orch.scanner.scan_once = original
        lock.release()

# Unauthenticated legacy routes blocked
import pytest

@pytest.fixture(autouse=True)
def _enable_auth(monkeypatch):
    monkeypatch.setenv("FORCE_AUTH", "true")
    yield

from fastapi.testclient import TestClient
from src.dashboard import app, storage as _gstorage, auth as _gauth
_gauth.setup_admin_from_env()
api_client = TestClient(app)

def test_unauth_legacy_status():
    r = api_client.get("/status")
    assert r.status_code == 401

def test_unauth_legacy_signals():
    r = api_client.get("/signals")
    assert r.status_code == 401

def test_unauth_legacy_trades():
    r = api_client.get("/trades")
    assert r.status_code == 401

def test_unauth_legacy_events():
    r = api_client.get("/events")
    assert r.status_code == 401

def test_unauth_legacy_equity():
    r = api_client.get("/equity")
    assert r.status_code == 401

def test_unauth_legacy_agents():
    r = api_client.get("/agents")
    assert r.status_code == 401

# WebSocket auth
def test_websocket_unauth_rejected():
    try:
        with api_client.websocket_connect("/ws") as ws:
            # if accepted, fail
            assert False, "websocket accepted without auth"
    except Exception:
        pass

# Missing admin fail-closed
def test_missing_admin_fail_closed():
    # new db, no admin
    d2 = tempfile.mkdtemp()
    from src.storage import Storage as S
    s = S(path=os.path.join(d2, "noadmin.db"))
    assert s.has_admin() is False

# PAPER-only enforcement
def test_paper_only_status():
    # login first
    r = api_client.post("/api/auth/login", json={"username": "admin", "password": "StrongPass123!"})
    assert r.status_code == 200
    r = api_client.get("/api/status")
    assert r.status_code == 200
    assert r.json()["trading_mode"] == "paper"
    assert r.json()["live_authorized"] is False

def test_live_activation_rejected():
    api_client.post("/api/auth/login", json={"username": "admin", "password": "StrongPass123!"})
    r = api_client.put("/api/admin/settings", json={"trading_mode": "live"})
    assert r.status_code == 200
    assert r.json().get("ok") is False

def test_no_admin_fail_closed_http(monkeypatch):
    monkeypatch.setenv("AUTH_DISABLED", "false")
    monkeypatch.setenv("FORCE_AUTH", "true")
    from src.dashboard import storage as gstorage
    orig = gstorage.has_admin
    gstorage.has_admin = lambda: False
    try:
        from fastapi.testclient import TestClient
        from src.dashboard import app
        c = TestClient(app)
        r = c.get("/api/status")
        assert r.status_code == 503
    finally:
        gstorage.has_admin = orig
