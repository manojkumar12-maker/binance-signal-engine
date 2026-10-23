import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from decimal import Decimal
from src.risk_engine import size_position, TradeProposal
from src.config import settings


def test_fee_aware_sizing():
    p = TradeProposal(symbol="BTCUSDT", direction="LONG", entry_price=Decimal("50000"), stop_loss_price=Decimal("49000"), take_profit_price=Decimal("53000"), leverage=2)
    d = size_position(p, Decimal("5"))
    assert d.approved is True
    assert d.quantity > 0
    assert d.estimated_loss <= settings.max_planned_loss_per_trade


def test_insufficient_margin_rejected():
    p = TradeProposal(symbol="BTCUSDT", direction="LONG", entry_price=Decimal("50000"), stop_loss_price=Decimal("49999"), take_profit_price=Decimal("50001"), leverage=1)
    # tiny stop distance -> huge qty -> margin exceeded
    d = size_position(p, Decimal("0.01"))
    assert d.approved is False


def test_zero_price_rejected():
    p = TradeProposal(symbol="BTCUSDT", direction="LONG", entry_price=Decimal("0"), stop_loss_price=Decimal("1"), take_profit_price=Decimal("2"), leverage=2)
    d = size_position(p, Decimal("5"))
    assert d.approved is False


def test_unacceptable_rr_rejected():
    p = TradeProposal(symbol="BTCUSDT", direction="LONG", entry_price=Decimal("50000"), stop_loss_price=Decimal("49000"), take_profit_price=Decimal("50100"), leverage=2)
    d = size_position(p, Decimal("5"))
    assert d.approved is False