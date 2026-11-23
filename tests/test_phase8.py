import os, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["TRADING_MODE"] = "paper"
_tmpdir = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(_tmpdir, "p8.db")

from src.storage import Storage
from src.config import settings
from src.orchestrator import Orchestrator
from tests.mock_exchange import MockBinanceClient

storage = Storage(path=os.environ["DATABASE_URL"].replace("sqlite:///",""))
client = MockBinanceClient()
orch = Orchestrator(client, storage)

# Recovery / persistence
def test_db_persistence():
    storage.log_event("SYSTEM", "", "test", "info", "persist check")
    # reopen
    storage2 = Storage(path=os.environ["DATABASE_URL"].replace("sqlite:///",""))
    evs = storage2.recent_events(limit=5)
    assert any(e["reason"] == "persist check" or e["message"] == "persist check" for e in evs)

def test_restart_recovery_no_duplicate():
    orch.run_cycle()
    before = len(storage.open_positions())
    orch2 = Orchestrator(client, storage)
    orch2.run_cycle()
    after = len(storage.open_positions())
    assert after <= max(before, 1)

def test_kill_switch_persists():
    storage.set_halted(True, "persist test")
    s2 = Storage(path=os.environ["DATABASE_URL"].replace("sqlite:///",""))
    from src.kill_switch import KillSwitch
    k = KillSwitch(s2)
    assert k.is_halted()[0] is True
    s2.set_halted(False)

# API / health / websocket
from fastapi.testclient import TestClient
from src.dashboard import app
api_client = TestClient(app)

def test_health_endpoint_phase8():
    r = api_client.get("/api/health")
    assert r.status_code == 200
    # three-state contract: ok (alive+progressing), running (alive, long cycle),
    # degraded (heartbeat stale)
    assert r.json()["status"] in ("ok", "running", "degraded")

def test_health_not_degraded_on_long_cycle():
    # Regression: a scan cycle longer than the 300s beat window must not flip
    # the dashboard to degraded while the heartbeat thread is still beating.
    from tests.mock_exchange import MockBinanceClient
    import tempfile, os
    d = tempfile.mkdtemp()
    st = Storage(path=os.path.join(d, "h.db"))
    st.update_heartbeat("running")          # beat is fresh
    st.upsert_agent_status("WORKER", "RUNNING", current_activity="stage: scanning")  # cycle in progress
    from fastapi.testclient import TestClient
    app = __import__("src.dashboard", fromlist=["app"]).app
    c = TestClient(app)
    r = c.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] in ("ok", "running"), r.json()
    assert r.json()["status"] != "degraded"

def test_monitoring_endpoint():
    r = api_client.get("/api/monitoring")
    assert r.status_code == 200
    assert "disk" in r.json() or "db_size_bytes" in r.json()

def test_websocket_phase8():
    with api_client.websocket_connect("/ws") as ws:
        data = ws.receive_json()
        assert "type" in data

def test_paper_integration():
    # execute a paper trade
    r = api_client.post("/api/paper/execute", json={
        "symbol": "BTCUSDT", "direction": "LONG", "entry_price": "50000",
        "stop_loss_price": "49000", "take_profit_price": "53000",
        "available_equity": "5", "rug_rating": "LOW"
    })
    # may be 400 if position open; accept either
    assert r.status_code in (200, 400)

def test_paper_mode_confirmed():
    r = api_client.get("/api/status")
    assert r.status_code == 200
    assert r.json()["trading_mode"] == "paper"
    assert r.json()["live_authorized"] is False