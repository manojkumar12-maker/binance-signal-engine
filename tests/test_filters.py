import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from decimal import Decimal
from src.exchange_filters import validate_order, round_quantity, round_price


def test_rounding():
    from decimal import Decimal
    assert round_quantity(Decimal("1.2345"), Decimal("0.001")) == Decimal("1.234")
    assert round_price(Decimal("50000.123"), Decimal("0.10")) == Decimal("50000.10")


def test_below_min_notional_rejected():
    info = {"symbols": [{"symbol": "BTCUSDT", "status": "TRADING", "filters": [
        {"filterType": "LOT_SIZE", "minQty": "0.001", "maxQty": "1000", "stepSize": "0.001"},
        {"filterType": "MIN_NOTIONAL", "notional": "100"},
    ]}]}
    ok, reason = validate_order(info, "BTCUSDT", Decimal("0.001"), Decimal("50000"))
    # 0.001*50000 = 50 < 100
    assert ok is False


def test_invalid_contract_rejected():
    info = {"symbols": [{"symbol": "BTCUSDT", "status": "TRADING", "filters": []}]}
    ok, reason = validate_order(info, "XRPUSDT", Decimal("1"), Decimal("1"))
    assert ok is False


def test_valid_order_accepted():
    info = {"symbols": [{"symbol": "BTCUSDT", "status": "TRADING", "filters": [
        {"filterType": "LOT_SIZE", "minQty": "0.001", "maxQty": "1000", "stepSize": "0.001"},
        {"filterType": "MIN_NOTIONAL", "notional": "100"},
    ]}]}
    ok, reason = validate_order(info, "BTCUSDT", Decimal("0.002"), Decimal("50000"))
    assert ok is True


def test_no_silent_risk_increase():
    # rounding down should not increase quantity
    assert round_quantity(Decimal("0.0019"), Decimal("0.001")) == Decimal("0.001")