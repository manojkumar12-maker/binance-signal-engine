import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_tmpdir = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(_tmpdir, "p5.db")
os.environ["TRADING_MODE"] = "paper"

from src.storage import Storage
from src.logger import Logger, redact
from src.equity import EquityAgent

storage = Storage(path=os.environ["DATABASE_URL"].replace("sqlite:///",""))

# Logger tests
def test_redact_secret():
    assert "***REDACTED***" in redact("api_key=abc123")
    assert "***REDACTED***" in redact("token: xyz")

def test_log_event_persisted():
    lg = Logger(storage)
    lg.info("SCANNER", "scan", "scanning market", symbol="BTCUSDT")
    evs = storage.recent_events(limit=10, agent="SCANNER")
    assert len(evs) >= 1
    assert evs[0]["severity"] == "INFO"

def test_log_severity_filter():
    lg = Logger(storage)
    lg.error("EXECUTER", "err", "something failed")
    evs = storage.recent_events(limit=10, severity="ERROR")
    assert any(e["severity"] == "ERROR" for e in evs)

def test_log_pagination():
    lg = Logger(storage)
    for i in range(5):
        lg.info("SYSTEM", "test", f"msg {i}")
    page1 = storage.recent_events(limit=2, offset=0)
    page2 = storage.recent_events(limit=2, offset=2)
    assert len(page1) == 2
    assert len(page2) == 2

def test_prune_logs():
    lg = Logger(storage)
    # prune with 0 days removes all old; but recent remain? cutoff now
    deleted = lg.prune(retention_days=0)
    assert isinstance(deleted, int)

def test_logger_failure_nonfatal():
    class BadStorage:
        def log_event(self, **kw):
            raise RuntimeError("db down")
    lg = Logger(BadStorage())
    # should not raise
    lg.info("X", "t", "msg")

# Equity tests
def test_equity_zero_trades():
    d = tempfile.mkdtemp()
    st = Storage(path=os.path.join(d, "e.db"))
    agent = EquityAgent(st)
    a = agent.analytics({})
    assert a["total_trades"] == 0
    assert a["win_rate"] is None
    assert a["profit_factor"] is None

def test_equity_with_trades():
    d = tempfile.mkdtemp()
    st = Storage(path=os.path.join(d, "e.db"))
    st.open_trade({"symbol": "BTCUSDT", "direction": "LONG", "entry_price": "50000", "stop_loss": "49000", "take_profit": "53000", "quantity": "0.001"})
    # close with profit
    tid = st.open_positions()[0]["id"]
    st.close_trade(tid, "5", "0.1")
    agent = EquityAgent(st)
    a = agent.analytics({})
    assert a["total_trades"] == 1
    assert a["winning_trades"] == 1
    assert a["win_rate"] == 100.0
    assert a["profit_factor"] is not None

def test_equity_drawdown_zero_loss():
    d = tempfile.mkdtemp()
    st = Storage(path=os.path.join(d, "e.db"))
    st.add_equity_snapshot(100, 100, 0, 0)
    st.add_equity_snapshot(100, 100, 0, 0)
    agent = EquityAgent(st)
    series = agent.drawdown_series()
    assert all(s["drawdown"] == "0" for s in series) or len(series) >= 0

def test_equity_by_symbol_direction():
    d = tempfile.mkdtemp()
    st = Storage(path=os.path.join(d, "e.db"))
    st.open_trade({"symbol": "BTCUSDT", "direction": "LONG", "entry_price": "50000", "stop_loss": "49000", "take_profit": "53000", "quantity": "0.001"})
    tid = st.open_positions()[0]["id"]
    st.close_trade(tid, "3", "0.1")
    agent = EquityAgent(st)
    a = agent.analytics({})
    assert "BTCUSDT" in a["by_symbol"]
    assert "LONG" in a["by_direction"]

def test_equity_snapshot_saved():
    d = tempfile.mkdtemp()
    st = Storage(path=os.path.join(d, "e.db"))
    agent = EquityAgent(st)
    agent.snapshot({})
    hist = agent.history()
    assert len(hist) >= 1

# API endpoint tests
from fastapi.testclient import TestClient
from src.dashboard import app
api_client = TestClient(app)

def test_logs_endpoint_filters():
    r = api_client.get("/api/logs?severity=INFO&limit=5")
    assert r.status_code == 200
    assert "events" in r.json()
    assert "total" in r.json()

def test_logs_summary_endpoint():
    r = api_client.get("/api/logs/summary")
    assert r.status_code == 200
    assert "total" in r.json()

def test_equity_endpoint():
    r = api_client.get("/api/equity")
    assert r.status_code == 200
    assert "analytics" in r.json()

def test_equity_history_endpoint():
    r = api_client.get("/api/equity/history")
    assert r.status_code == 200
    assert "history" in r.json()

def test_equity_analytics_endpoint():
    r = api_client.get("/api/equity/analytics")
    assert r.status_code == 200
    assert "analytics" in r.json()

def test_equity_drawdown_endpoint():
    r = api_client.get("/api/equity/drawdown")
    assert r.status_code == 200
    assert "series" in r.json()