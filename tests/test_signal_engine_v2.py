"""Regression tests for Signal Engine V2 candidate promotion."""
from decimal import Decimal

from src.signal_engine import SignalEngine


class _Cfg:
    min_signal_score = Decimal("0")
    volume_ratio_min = Decimal("0")
    adx_trend_min = Decimal("0")
    atr_pct_max = Decimal("100")
    sl_atr_mult = Decimal("1.5")
    tp_atr_mult = Decimal("3.0")
    pullback_tolerance_atr = Decimal("0.5")
    breakout_lookback = 20
    max_extended_candle_atr = Decimal("10")
    min_reward_to_risk = Decimal("1")


def _trend_klines(n=150, start=Decimal("100")):
    rows = []
    for i in range(n):
        o = start + Decimal(i)
        c = o + Decimal("0.5")
        h = c + Decimal("0.2")
        low = o - Decimal("0.2")
        rows.append([i * 900000, str(o), str(h), str(low), str(c), "1000"])
    return rows


def test_v2_scores_can_produce_signal():
    engine = SignalEngine(cfg=_Cfg())
    sig, diag = engine.evaluate_v2("TESTUSDT", _trend_klines())
    assert diag.final_decision == "SIGNAL"
    assert sig is not None
    assert sig.direction == "LONG"
    assert sig.score >= 0
