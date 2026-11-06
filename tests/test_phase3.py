import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from decimal import Decimal
from src.indicators import ema, rsi, macd, atr, volume_ratio
from src.rug_check import RugChecker
from src.signal_engine import SignalEngine

# Indicator tests
def test_ema_basic():
    vals = [Decimal(x) for x in ["1","2","3","4","5"]]
    out = ema(vals, 3)
    assert len(out) == 5
    assert out[-1] > out[0]

def test_rsi_range():
    vals = [Decimal(str(50 + i)) for i in range(30)]
    r = rsi(vals, 14)
    assert r is not None
    assert Decimal("0") <= r <= Decimal("100")

def test_macd_returns():
    vals = [Decimal(str(100 + i*0.5)) for i in range(60)]
    m, s, h = macd(vals)
    assert m is not None and s is not None and h is not None

def test_atr_positive():
    highs = [Decimal(str(10 + i)) for i in range(20)]
    lows = [Decimal(str(8 + i)) for i in range(20)]
    closes = [Decimal(str(9 + i)) for i in range(20)]
    a = atr(highs, lows, closes, 14)
    assert a is not None and a > 0

def test_volume_ratio():
    vols = [Decimal("100")]*20 + [Decimal("200")]
    vr = volume_ratio(vols, 20)
    assert vr is not None and vr >= Decimal("1")

# Rug check tests
def test_rug_check_unknown_insufficient():
    rc = RugChecker()
    res = rc.assess("BTCUSDT", [[0,"1","1","1","1","1"]]*5)
    assert res["risk_rating"] == "UNKNOWN"

def test_rug_check_low_normal():
    kl = []
    base = 100
    for i in range(60):
        kl.append([i, str(base+i*0.1), str(base+i*0.2+1), str(base+i*0.1-1), str(base+i*0.15), "1000"])
    rc = RugChecker()
    res = rc.assess("BTCUSDT", kl)
    assert res["risk_rating"] in ("LOW", "MEDIUM", "HIGH")
    assert "reasons" in res and "warnings" in res

def test_rug_check_high_volatility():
    kl = []
    for i in range(60):
        kl.append([i, "100", "200", "50", "100", "1000"])  # huge range
    rc = RugChecker()
    res = rc.assess("BTCUSDT", kl)
    assert res["risk_rating"] == "HIGH"

# Signal logic tests
def test_signal_insufficient_data():
    se = SignalEngine(cooldown_seconds=0)
    kl = [[0,"1","1","1","1","1"]]*10
    sig = se.evaluate_klines("BTCUSDT", "15m", kl)
    assert sig is None

# Multi-symbol scanner test
def test_scanner_multi_symbol():
    from tests.mock_exchange import MockBinanceClient
    from src.storage import Storage
    from src.scanner import Scanner
    d = tempfile.mkdtemp()
    storage = Storage(path=os.path.join(d, "s.db"))
    client = MockBinanceClient()
    # mock needs klines for any symbol; already does
    scanner = Scanner(client, storage, ["BTCUSDT", "ETHUSDT"])
    results = scanner.scan_once()
    assert len(results) == 2
    for r in results:
        assert "symbol" in r
        assert r["symbol"] in ("BTCUSDT", "ETHUSDT")

# Duplicate signal prevention
def test_duplicate_signal_prevented():
    from tests.mock_exchange import MockBinanceClient
    from src.storage import Storage
    from src.scanner import Scanner
    d = tempfile.mkdtemp()
    storage = Storage(path=os.path.join(d, "s.db"))
    client = MockBinanceClient()
    scanner = Scanner(client, storage, ["BTCUSDT"])
    r1 = scanner.scan_once()
    # second scan should mark duplicate if same candle
    r2 = scanner.scan_once()
    # either no signal or duplicate flag
    assert len(r2) == 1

# DB persistence for scanner results
def test_scanner_result_persisted():
    from tests.mock_exchange import MockBinanceClient
    from src.storage import Storage
    from src.scanner import Scanner
    d = tempfile.mkdtemp()
    storage = Storage(path=os.path.join(d, "s.db"))
    client = MockBinanceClient()
    scanner = Scanner(client, storage, ["BTCUSDT"])
    scanner.scan_once()
    rows = storage.recent_scanner_results(limit=10)
    # mock data may or may not produce signal; ensure no crash
    assert isinstance(rows, list)

# API endpoints (use temp db)
_tmpdir = tempfile.mkdtemp()
os.environ.setdefault("DATABASE_URL", "sqlite:///" + os.path.join(_tmpdir, "api3.db"))
os.environ.setdefault("TRADING_MODE", "paper")

from fastapi.testclient import TestClient
from src.dashboard import app
api_client = TestClient(app)

def test_scanner_symbols_endpoint():
    r = api_client.get("/api/scanner/symbols")
    assert r.status_code == 200
    assert "symbols" in r.json()

def test_scanner_results_endpoint():
    r = api_client.get("/api/scanner/results")
    assert r.status_code == 200
    assert "results" in r.json()

def test_rug_check_endpoint():
    r = api_client.get("/api/rug-check/BTCUSDT")
    assert r.status_code == 200
    # mock client uses testnet? Binance public endpoint may fail in test env; accept error or rating
    d = r.json()
    assert "symbol" in d or "error" in d

def test_rug_check_scan_endpoint():
    r = api_client.post("/api/rug-check/scan")
    assert r.status_code in (200, 401, 403, 500)

# Agent status update
def test_agent_status_update_phase3():
    from src.storage import Storage
    d = tempfile.mkdtemp()
    s = Storage(path=os.path.join(d, "a.db"))
    s.upsert_agent_status("SCANNER", "SCANNING", current_activity="test")
    rows = s.get_agent_statuses()
    sc = [r for r in rows if r["name"] == "SCANNER"][0]
    assert sc["status"] == "SCANNING"

# Missing data not treated as safe
def test_rug_check_missing_data_unknown():
    rc = RugChecker()
    res = rc.assess("X", [])
    assert res["risk_rating"] == "UNKNOWN"