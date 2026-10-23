import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from decimal import Decimal
from tests.mock_exchange import MockBinanceClient
from src.storage import Storage
from src.execution import ExecutionEngine


def test_no_live_order_without_marker():
    d = tempfile.mkdtemp()
    db = os.path.join(d, "t.db")
    storage = Storage(path=db)
    client = MockBinanceClient()
    info = client.exchange_info()
    eng = ExecutionEngine(client, storage, info)
    # simulate all flags true but no marker file
    import src.config as cfg
    cfg.settings.trading_mode = "live"
    cfg.settings.broker_enabled = True
    cfg.settings.auto_trade = True
    cfg.settings.live_trading_enabled = True
    cfg.settings.use_testnet = False
    cfg.settings.binance_api_key = "k"
    cfg.settings.binance_api_secret = "s"
    class Sig:
        symbol = "BTCUSDT"; direction = "LONG"; entry_price = Decimal("50000")
        stop_loss = Decimal("49000"); take_profit = Decimal("53000")
    ok, reason = eng.execute_signal(Sig(), "BTCUSDT")
    # should record only, not place real order
    assert ok is True
    assert "recorded" in reason
    assert len(client.placed_orders) == 0
    # restore
    cfg.settings.trading_mode = "demo"