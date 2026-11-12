import os
import sys
import tempfile
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import settings
from src.execution import ExecutionEngine, exchange_execution_authorized
from src.storage import Storage
from tests.mock_exchange import MockBinanceClient


class Sig:
    signal_id = "BTCUSDT:LONG:breakout:1700000000000"
    direction = "LONG"
    entry_price = Decimal("50000")
    stop_loss = Decimal("49000")
    take_profit = Decimal("53000")


class Size:
    quantity = Decimal("0.001")


def _engine():
    storage = Storage(path=os.path.join(tempfile.mkdtemp(), "exec.db"))
    client = MockBinanceClient()
    return ExecutionEngine(client, storage, client.exchange_info()), storage, client


def _demo_settings(monkeypatch):
    monkeypatch.setattr(settings, "trading_mode", "paper")
    monkeypatch.setattr(settings, "use_testnet", True)
    monkeypatch.setattr(settings, "binance_testnet_api_key", "demo-key")
    monkeypatch.setattr(settings, "binance_testnet_api_secret", "demo-secret")


def test_demo_execution_places_market_and_stop(monkeypatch):
    _demo_settings(monkeypatch)
    assert exchange_execution_authorized() is True
    eng, storage, client = _engine()
    ok, reason = eng.execute_signal(Sig(), "BTCUSDT", size_decision=Size())
    assert ok is True and reason == "executed"
    types = [o.get("type") for o in client.placed_orders]
    assert "MARKET" in types
    assert "STOP_MARKET" in types
    market = next(o for o in client.placed_orders if o.get("type") == "MARKET")
    assert market.get("newOrderRespType") == "RESULT"
    assert market.get("quantity") == "0.001"
    stop = next(o for o in client.placed_orders if o.get("type") == "STOP_MARKET")
    assert stop.get("closePosition") == "true"
    assert "reduceOnly" not in stop
    assert Decimal(stop.get("stopPrice")) == Decimal("49000")
    trades = storage.open_positions()
    assert len(trades) == 1
    assert trades[0]["entry_order_id"] == str(market["id"])


def test_no_demo_keys_falls_back_to_record_only(monkeypatch):
    monkeypatch.setattr(settings, "trading_mode", "paper")
    monkeypatch.setattr(settings, "use_testnet", True)
    monkeypatch.setattr(settings, "binance_testnet_api_key", "")
    monkeypatch.setattr(settings, "binance_testnet_api_secret", "")
    assert exchange_execution_authorized() is False
    eng, storage, client = _engine()
    ok, reason = eng.execute_signal(Sig(), "BTCUSDT", size_decision=Size())
    assert ok is True
    assert "recorded" in reason
    assert client.placed_orders == []


def test_monitor_marks_closed_and_replaces_missing_stop(monkeypatch):
    _demo_settings(monkeypatch)
    eng, storage, client = _engine()
    storage.open_trade({
        "symbol": "BTCUSDT", "direction": "LONG", "entry_price": "50000",
        "stop_loss": "49000", "take_profit": "53000", "quantity": "0.001",
        "entry_order_id": "1", "stop_order_id": "2",
    })
    client.positions = [{"symbol": "BTCUSDT", "positionAmt": "0.001"}]
    client.open_orders_list = []
    actions = eng.monitor()
    assert any(a["action"] == "stop_replaced" for a in actions)
    assert any(o.get("type") == "STOP_MARKET" for o in client.placed_orders)
    assert len(storage.open_positions()) == 1

    client.positions = []
    actions = eng.monitor()
    assert any(a["action"] == "closed_on_exchange" for a in actions)
    assert storage.open_positions() == []
