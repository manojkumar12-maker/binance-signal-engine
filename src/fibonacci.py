"""Fibonacci level calculations.

Retracement levels for entry zones and extension levels for targets,
computed from a swing high/low window on closed candles only.
"""
from decimal import Decimal
from typing import Optional

RETRACEMENTS = (Decimal("0.236"), Decimal("0.382"), Decimal("0.5"),
                Decimal("0.618"), Decimal("0.786"))
EXTENSIONS = (Decimal("1.272"), Decimal("1.618"), Decimal("2.0"), Decimal("2.618"))


def swing(highs: list[Decimal], lows: list[Decimal], lookback: int = 55
          ) -> tuple[Decimal, Decimal, int, int]:
    """Return (swing_high, swing_low, idx_high, idx_low) over the last `lookback` candles."""
    n = min(lookback, len(highs), len(lows))
    window_h = highs[-n:]
    window_l = lows[-n:]
    hi = max(window_h)
    lo = min(window_l)
    return hi, lo, len(window_h) - 1 - window_h[::-1].index(hi), len(window_l) - 1 - window_l[::-1].index(lo)


def retracements(high: Decimal, low: Decimal, direction: str) -> dict[str, Decimal]:
    """Retracement price levels for a swing from low to high (LONG) or high to low (SHORT)."""
    out = {}
    span = high - low
    for r in RETRACEMENTS:
        if direction == "LONG":
            out[str(r)] = high - span * r
        else:
            out[str(r)] = low + span * r
    return out


def extensions(high: Decimal, low: Decimal, direction: str) -> dict[str, Decimal]:
    """Extension price levels beyond the swing, used for take-profit targets."""
    out = {}
    span = high - low
    for e in EXTENSIONS:
        if direction == "LONG":
            out[str(e)] = low + span * e
        else:
            out[str(e)] = high - span * e
    return out


def golden_pocket(direction: str, high: Decimal, low: Decimal) -> tuple[Decimal, Decimal]:
    """The 0.618-0.65 retracement zone, the preferred Fib entry band."""
    span = high - low
    if direction == "LONG":
        return high - span * Decimal("0.618"), high - span * Decimal("0.65")
    return low + span * Decimal("0.618"), low + span * Decimal("0.65")


def fib_target(direction: str, entry: Decimal, stop: Decimal,
               high: Decimal, low: Decimal) -> Optional[Decimal]:
    """Choose the nearest Fib extension beyond entry in the trade direction.

    Falls back to None if no extension lies beyond entry (degenerate swing).
    """
    exts = extensions(high, low, direction)
    cands = [p for p in exts.values() if (p > entry if direction == "LONG" else p < entry)]
    if not cands:
        return None
    if direction == "LONG":
        return min(cands, key=lambda p: p - entry)
    return max(cands, key=lambda p: entry - p)
