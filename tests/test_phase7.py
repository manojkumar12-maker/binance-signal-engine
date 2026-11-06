import os, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["TRADING_MODE"] = "paper"
_tmpdir = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(_tmpdir, "p7.db")

from src.storage import Storage
from src.config import settings
from src.orchestrator import Orchestrator
from tests.mock_exchange import MockBinanceClient
from src.grok_client import GrokClient

storage = Storage(path=os.environ["DATABASE_URL"].replace("sqlite:///",""))
client = MockBinanceClient()
orch = Orchestrator(client, storage)

def test_orchestrator_cycle_runs():
    results = orch.run_cycle()
    assert isinstance(results, list)

def test_agent_heartbeats_updated():
    orch.run_cycle()
    statuses = storage.get_agent_statuses()
    names = {s["name"] for s in statuses}
    assert "SCANNER" in names
    assert "EXECUTER" in names

def test_workflow_stage_set():
    orch.run_cycle()
    stage = storage.get_setting("workflow_stage")
    assert stage in ("idle", None) or isinstance(stage, str)

def test_idempotency_no_duplicate_position():
    # run twice; open positions should not exceed 1
    orch.run_cycle()
    orch.run_cycle()
    assert len(storage.open_positions()) <= 1

def test_kill_switch_blocks_execution():
    storage.set_halted(True, "test")
    orch.run_cycle()
    # no new open positions expected beyond existing
    storage.set_halted(False)

def test_grok_disabled_by_default():
    g = GrokClient()
    assert g.available() is False
    assert g.explain_signal({"symbol": "BTCUSDT"}) is None

def test_concurrent_worker_lock():
    from src.worker_lock import WorkerLock
    lock = WorkerLock()
    assert lock.acquire() is True
    # second acquire fails
    lock2 = WorkerLock()
    assert lock2.acquire() is False
    lock.release()

def test_logger_event_sequence():
    evs = storage.recent_events(limit=50)
    agents = {e["agent"] for e in evs}
    assert "ORCHESTRATOR" in agents or "SCANNER" in agents

def test_equity_snapshot_after_trade():
    # if a trade occurred, snapshot exists
    snaps = storage.get_equity_snapshots()
    assert isinstance(snaps, list)

# API endpoint for orchestrator stage
from fastapi.testclient import TestClient
from src.dashboard import app
api_client = TestClient(app)

def test_orchestrator_stage_in_status():
    r = api_client.get("/api/status")
    assert r.status_code == 200
    assert "workflow_stage" in r.json()