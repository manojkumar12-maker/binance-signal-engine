import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.mock_exchange import MockBinanceClient
from src.storage import Storage
from src.reconciliation import ReconciliationService
from src.config import settings


def _run_as_testnet(fn):
    orig = settings.trading_mode
    settings.trading_mode = "testnet"
    try:
        return fn()
    finally:
        settings.trading_mode = orig


def test_recon_unknown_position():
    def body():
        d = tempfile.mkdtemp()
        db = os.path.join(d, "t.db")
        s = Storage(path=db)
        client = MockBinanceClient()
        client.positions = [{"symbol": "BTCUSDT", "positionAmt": "0.001"}]
        recon = ReconciliationService(client, s)
        r = recon.reconcile()
        assert any("unknown exchange position" in x for x in r["discrepancies"])
    _run_as_testnet(body)


def test_recon_stale_local():
    def body():
        d = tempfile.mkdtemp()
        db = os.path.join(d, "t.db")
        s = Storage(path=db)
        s.open_trade({"symbol": "BTCUSDT", "direction": "LONG", "entry_price": "50000", "stop_loss": "49000", "take_profit": "53000", "quantity": "0.001"})
        client = MockBinanceClient()
        client.positions = []
        recon = ReconciliationService(client, s)
        r = recon.reconcile()
        assert any("local open but exchange closed" in x for x in r["discrepancies"])
        assert len(s.open_positions()) == 0
    _run_as_testnet(body)
