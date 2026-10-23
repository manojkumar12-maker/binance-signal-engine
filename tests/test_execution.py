import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from decimal import Decimal
from src.execution import ExecutionEngine
from src.storage import Storage
from tests.mock_exchange import MockBinanceClient
import tempfile, os as _os


def _make_engine():
    tmpdir = tempfile.mkdtemp()
    db = _os.path.join(tmpdir, "t.db")
    storage = Storage(path=db)
    client = MockBinanceClient()
    info = client.exchange_info()
    return ExecutionEngine(client, storage, info), storage, client


def test_duplicate_signal_prevented_by_position():
    eng, storage, client = _make_engine()
    # simulate open position on exchange
    client.positions = [{"symbol": "BTCUSDT", "positionAmt": "0.001"}]
    # craft a fake signal object
    class Sig:
        symbol="BTCUSDT"
        direction = "LONG"
        entry_price = Decimal("50000")
        stop_loss = Decimal("49000")
        take_profit = Decimal("53000")
    ok, reason = eng.execute_signal(Sig(), "BTCUSDT")
    assert ok is False
    assert "position" in reason or "max" in reason


def test_live_disabled_records_only():
    eng, storage, client = _make_engine()
    class Sig:
        symbol="BTCUSDT"
        direction = "LONG"
        entry_price = Decimal("50000")
        stop_loss = Decimal("49000")
        take_profit = Decimal("53000")
    ok, reason = eng.execute_signal(Sig(), "BTCUSDT")
    # live not authorized -> recorded only
    assert ok is True
    assert "recorded" in reason or "live" in reason


def test_one_position_rule_central():
    eng, storage, client = _make_engine()
    storage.open_trade({"symbol": "BTCUSDT", "direction": "LONG", "entry_price": "50000", "stop_loss": "49000", "take_profit": "52000", "quantity": "0.001"})
    class Sig:
        symbol="BTCUSDT"
        direction = "LONG"
        entry_price = Decimal("50000")
        stop_loss = Decimal("49000")
        take_profit = Decimal("53000")
    ok, reason = eng.execute_signal(Sig(), "BTCUSDT")
    assert ok is False