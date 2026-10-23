import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from decimal import Decimal
from tests.mock_exchange import MockBinanceClient
from src.storage import Storage
from src.execution import ExecutionEngine


def test_marker_alone_insufficient():
    d = tempfile.mkdtemp()
    db = os.path.join(d, "t.db")
    storage = Storage(path=db)
    client = MockBinanceClient()
    info = client.exchange_info()
    eng = ExecutionEngine(client, storage, info)
    # create marker file but keep flags disabled
    marker = os.path.join(d, "LIVE_ACTIVATED")
    os.makedirs(os.path.join(d, "data"), exist_ok=True)
    with open(os.path.join("data", "LIVE_ACTIVATED"), "w") as f:
        f.write("x")
    import src.config as cfg
    cfg.settings.trading_mode = "demo"
    cfg.settings.broker_enabled = False
    cfg.settings.auto_trade = False
    cfg.settings.live_trading_enabled = False
    class Sig:
        symbol = "BTCUSDT"; direction = "LONG"; entry_price = Decimal("50000")
        stop_loss = Decimal("49000"); take_profit = Decimal("53000")
    ok, reason = eng.execute_signal(Sig(), "BTCUSDT")
    assert ok is True
    assert "recorded" in reason
    assert len(client.placed_orders) == 0
    # cleanup marker
    try:
        os.remove(os.path.join("data", "LIVE_ACTIVATED"))
    except FileNotFoundError:
        pass