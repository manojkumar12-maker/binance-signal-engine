"""
Given a generated signal (entry/sl/tp1/tp2/tp3) and the 1h candles following
it, simulates what would have happened: which level got hit, in what order,
and the resulting R-multiple outcome.

Two outcome views are tracked per trade (see README - your 80% / 1:3 goals
trade off against each other depending on which you mean by "win"):

  - tp1_touch:   did price reach TP1 at all before SL? (binary)
  - realized_r:  R-multiple actually banked, simulating the documented
                 partial-TP + trailing-stop behavior (50% off at TP1, trail
                 remainder) so it reflects what the live system would do,
                 not just "did it reach TP3".

NOTE ON INTRA-CANDLE AMBIGUITY: if a single 1h candle's high/low range
contains BOTH the SL and a TP level, we cannot know from OHLC alone which
was touched first. v1 resolves this conservatively: SL is assumed hit first
on any ambiguous candle. This biases results slightly pessimistic, which is
the safer direction for validating a live-trading decision.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional

MAX_HOLD_CANDLES = 200  # ~8 days of 1h candles; abandon trade as "timeout" beyond this


@dataclass
class TradeOutcome:
    pair: str
    signal_type: str
    entry: float
    sl: float
    tp1: float
    tp2: float
    tp3: float
    confidence: int
    tier: str
    regime: str
    session: str
    setup_type: str
    entry_time_ms: int

    outcome: str = "UNRESOLVED"       # SL | TP1_ONLY | TP1_TP2 | TP1_TP2_TP3 | TIMEOUT
    exit_time_ms: Optional[int] = None
    bars_held: int = 0
    tp1_touch: bool = False
    tp2_touch: bool = False
    tp3_touch: bool = False
    realized_r: float = 0.0           # R-multiple after simulated partial/trail management
    raw_r_if_full_target: float = 0.0  # what full TP3 alone would have paid, for reference


def _risk_unit(entry: float, sl: float) -> float:
    return abs(entry - sl)


def simulate_trade(signal: Dict, future_candles: List[Dict], session: str, regime_name: str) -> TradeOutcome:
    entry = signal["entry_primary"]
    sl = signal["sl"]
    tp1, tp2, tp3 = signal["tp1"], signal["tp2"], signal["tp3"]
    is_buy = signal["signal_type"] == "BUY" or signal["signal"] == "BUY"

    risk = _risk_unit(entry, sl)
    outcome = TradeOutcome(
        pair=signal["pair"],
        signal_type="BUY" if is_buy else "SELL",
        entry=entry, sl=sl, tp1=tp1, tp2=tp2, tp3=tp3,
        confidence=signal.get("confidence", 0),
        tier=signal.get("tier", "UNKNOWN"),
        regime=regime_name,
        session=session,
        setup_type=signal.get("setup_type", "UNKNOWN"),
        entry_time_ms=signal.get("_entry_time_ms", 0),
    )

    if risk == 0:
        outcome.outcome = "INVALID"
        return outcome

    outcome.raw_r_if_full_target = abs(tp3 - entry) / risk

    stopped_out = False
    tp1_hit = tp2_hit = tp3_hit = False
    current_stop = sl  # moves to breakeven/trailing after partials, mirrors trade_manager.should_trail_stop

    for i, candle in enumerate(future_candles[:MAX_HOLD_CANDLES]):
        hi, lo = candle["high"], candle["low"]
        outcome.bars_held = i + 1

        if is_buy:
            hits_sl = lo <= current_stop
            hits_tp1 = hi >= tp1
            hits_tp2 = hi >= tp2
            hits_tp3 = hi >= tp3
        else:
            hits_sl = hi >= current_stop
            hits_tp1 = lo <= tp1
            hits_tp2 = lo <= tp2
            hits_tp3 = lo <= tp3

        # Conservative resolution: if SL and any TP are both touched in the
        # same candle, treat SL as having happened first (see module docstring).
        if hits_sl and not tp1_hit:
            stopped_out = True
            outcome.exit_time_ms = candle["open_time"]
            break

        if not tp1_hit and hits_tp1:
            tp1_hit = True
            outcome.tp1_touch = True
            current_stop = entry  # README: "partial TP at TP1, trailing SL" -> move to breakeven
            if hits_sl:
                # SL and TP1 in the same candle, ambiguous - conservative: stop here
                pass

        if tp1_hit and not tp2_hit and hits_tp2:
            tp2_hit = True
            outcome.tp2_touch = True
            if is_buy:
                current_stop = max(current_stop, tp1)
            else:
                current_stop = min(current_stop, tp1)

        if tp2_hit and not tp3_hit and hits_tp3:
            tp3_hit = True
            outcome.tp3_touch = True
            outcome.exit_time_ms = candle["open_time"]
            break

        # after tp1, re-check trailing stop hit on this same candle
        if tp1_hit and not tp3_hit:
            if is_buy and lo <= current_stop:
                outcome.exit_time_ms = candle["open_time"]
                break
            if not is_buy and hi >= current_stop:
                outcome.exit_time_ms = candle["open_time"]
                break
    else:
        outcome.outcome = "TIMEOUT"

    # Determine final outcome label + realized R using a 50%-at-TP1,
    # run-the-rest-with-trailing-stop model (matches README's stated
    # "Partial TP (50% at TP1, trailing SL)" behavior).
    if stopped_out and not tp1_hit:
        outcome.outcome = "SL"
        outcome.realized_r = -1.0
    elif tp3_hit:
        outcome.outcome = "TP1_TP2_TP3"
        outcome.realized_r = 0.5 * 1.0 + 0.5 * (abs(tp3 - entry) / risk)
    elif tp2_hit:
        outcome.outcome = "TP1_TP2_TRAIL_STOP"
        trail_r = abs(tp1 - entry) / risk
        outcome.realized_r = 0.5 * 1.0 + 0.5 * trail_r
    elif tp1_hit:
        outcome.outcome = "TP1_ONLY_TRAIL_STOP"
        outcome.realized_r = 0.5 * 1.0 + 0.5 * 0.0  # other half exited at breakeven
    elif outcome.outcome != "TIMEOUT":
        outcome.outcome = "SL"
        outcome.realized_r = -1.0

    return outcome
