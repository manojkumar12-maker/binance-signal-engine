import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from decimal import Decimal
from tests.mock_exchange import MockBinanceClient
from src.storage import Storage
from src.execution import ExecutionEngine
import src.execution as execution


def test_marker_alone_insufficient(monkeypatch):
    d = tempfile.mkdtemp()
    db = os.path.join(d, "t.db")
    storage = Storage(path=db)
    client = MockBinanceClient()
    info = client.exchange_info()
    eng = ExecutionEngine(client, storage, info)
    # create marker file but keep live flags disabled
    marker = os.path.join(d, "LIVE_ACTIVATED")
    with open(marker, "w") as f:
        f.write("x")
    # execution reads LIVE_MARKER relative to cwd; point it at the temp marker
    monkeypatch.setattr(execution, "LIVE_MARKER", marker)
    import src.config as cfg
    monkeypatch.setattr(cfg.settings, "trading_mode", "demo")
    monkeypatch.setattr(cfg.settings, "broker_enabled", False)
    monkeypatch.setattr(cfg.settings, "auto_trade", False)
    monkeypatch.setattr(cfg.settings, "live_trading_enabled", False)
    class Sig:
        symbol = "BTCUSDT"; direction = "LONG"; entry_price = Decimal("50000")
        stop_loss = Decimal("49000"); take_profit = Decimal("53000")
    ok, reason = eng.execute_signal(Sig(), "BTCUSDT")
    assert ok is True
    assert "recorded" in reason
    assert len(client.placed_orders) == 0
