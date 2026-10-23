import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from decimal import Decimal
from src.storage import Storage
from src.kill_switch import KillSwitch


def test_kill_switch_persists():
    d = tempfile.mkdtemp()
    db = os.path.join(d, "t.db")
    s1 = Storage(path=db)
    k1 = KillSwitch(s1)
    k1.halt("test")
    assert k1.is_halted()[0] is True
    s1.close()

    s2 = Storage(path=db)
    k2 = KillSwitch(s2)
    assert k2.is_halted()[0] is True
    assert "test" in k2.is_halted()[1]


def test_daily_loss_triggers_halt():
    d = tempfile.mkdtemp()
    db = os.path.join(d, "t.db")
    s = Storage(path=db)
    k = KillSwitch(s)
    # max daily loss 0.10; record 0.10
    k.record_trade_result(Decimal("-0.10"))
    assert k.is_halted()[0] is True


def test_reset_requires_confirmation():
    d = tempfile.mkdtemp()
    db = os.path.join(d, "t.db")
    s = Storage(path=db)
    k = KillSwitch(s)
    k.halt("x")
    try:
        k.reset(operator_confirmed=False)
        raised = False
    except RuntimeError:
        raised = True
    assert raised is True