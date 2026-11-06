import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Use isolated DB for API tests
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(_tmp, "api.db")
os.environ["TRADING_MODE"] = "paper"
os.environ["ADMIN_TOKEN"] = ""

from fastapi.testclient import TestClient
from src.dashboard import app

client = TestClient(app)


def test_health_endpoint():
    r = client.get("/api/health")
    assert r.status_code == 200
    d = r.json()
    assert "status" in d
    assert d["mode"] in ("paper", "demo")


def test_status_endpoint():
    r = client.get("/api/status")
    assert r.status_code == 200
    d = r.json()
    assert "trading_mode" in d
    assert "agent_statuses" in d


def test_agents_endpoint():
    r = client.get("/api/agents")
    assert r.status_code == 200
    d = r.json()
    assert len(d["agents"]) == 7
    for a in d["agents"]:
        assert "name" in a and "status" in a


def test_db_tables_initialized():
    from src.storage import Storage
    s = Storage(path=os.path.join(_tmp, "api.db"))
    cur = s.conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    names = {r[0] for r in cur.fetchall()}
    for t in ["agent_status", "events", "trades", "signals", "orders", "positions", "equity_snapshots", "admin_actions", "settings"]:
        assert t in names, t


def test_agent_status_values():
    from src.storage import Storage
    s = Storage(path=os.path.join(_tmp, "api.db"))
    s.upsert_agent_status("SCANNER", "SCANNING", current_activity="test")
    rows = s.get_agent_statuses()
    sc = [r for r in rows if r["name"] == "SCANNER"][0]
    assert sc["status"] == "SCANNING"


def test_heartbeat():
    from src.storage import Storage
    s = Storage(path=os.path.join(_tmp, "api.db"))
    s.update_heartbeat("running")
    hb = s.get_heartbeat()
    assert hb["status"] == "running"
    assert hb["last_beat"] is not None


def test_paper_demo_compat():
    from src.config import Settings
    s1 = Settings(trading_mode="demo")
    s2 = Settings(trading_mode="paper")
    assert s1.normalized_mode == "paper"
    assert s2.normalized_mode == "paper"
    assert s1.paper_mode and s2.paper_mode


def test_kill_switch():
    from src.storage import Storage
    from src.kill_switch import KillSwitch
    from decimal import Decimal
    d = tempfile.mkdtemp()
    st = Storage(path=os.path.join(d, "k.db"))
    k = KillSwitch(st)
    k.halt("test")
    assert k.is_halted()[0] is True
    k.reset(operator_confirmed=True)
    assert k.is_halted()[0] is False


def test_websocket_connectivity():
    with client.websocket_connect("/ws") as ws:
        data = ws.receive_json()
        assert "type" in data


def test_logs_endpoint():
    r = client.get("/api/logs")
    assert r.status_code == 200
    assert "events" in r.json()


def test_equity_endpoint():
    r = client.get("/api/equity")
    assert r.status_code == 200
    assert "equity" in r.json()


def test_positions_endpoint():
    r = client.get("/api/positions")
    assert r.status_code == 200
    assert "positions" in r.json()


def test_trades_endpoint():
    r = client.get("/api/trades")
    assert r.status_code == 200
    assert "trades" in r.json()


def test_signals_endpoint():
    r = client.get("/api/signals")
    assert r.status_code == 200
    assert "signals" in r.json()


def test_account_endpoint():
    r = client.get("/api/account")
    assert r.status_code == 200
    assert "mode" in r.json()


def test_market_endpoint():
    r = client.get("/api/market")
    assert r.status_code == 200


def test_settings_endpoint():
    r = client.get("/api/settings")
    assert r.status_code == 200
    assert "trading_mode" in r.json()


def test_scanner_start_stop():
    r = client.post("/api/scanner/start")
    assert r.status_code == 200
    r = client.post("/api/scanner/stop")
    assert r.status_code == 200


def test_system_kill():
    r = client.post("/api/system/kill")
    assert r.status_code == 200
    assert r.json().get("halted") is True
    # resume
    client.post("/api/system/kill")  # no-op re-halt
    # reset via resume endpoint
    client.post("/resume")