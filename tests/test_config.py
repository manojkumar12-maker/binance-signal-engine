import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from decimal import Decimal
from src.config import Settings


def test_default_balance_5():
    s = Settings()
    assert s.simulated_starting_balance == Decimal("5.0")


def test_live_disabled_by_default():
    s = Settings()
    assert s.broker_enabled is False
    assert s.auto_trade is False
    assert s.live_trading_enabled is False
    assert s.live_authorized is False


def test_invalid_risk_settings_rejected():
    import pytest
    with pytest.raises(Exception):
        Settings(max_daily_loss_usdt=Decimal("-1"))


def test_missing_credentials_prevent_live():
    s = Settings(trading_mode="live", broker_enabled=True, auto_trade=True, live_trading_enabled=True, use_testnet=False)
    # credentials empty => live_authorized false
    assert s.live_authorized is False