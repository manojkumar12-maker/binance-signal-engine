"""Technical indicator calculations."""
from decimal import Decimal
from typing import Optional


def ema(values: list[Decimal], period: int) -> list[Decimal]:
    if not values:
        return []
    k = Decimal(2) / (Decimal(period) + Decimal(1))
    out = [values[0]]
    for v in values[1:]:
        out.append(v * k + out[-1] * (Decimal(1) - k))
    return out


def rsi(values: list[Decimal], period: int = 14) -> Optional[Decimal]:
    if len(values) < period + 1:
        return None
    gains = []
    losses = []
    for i in range(1, period + 1):
        diff = values[i] - values[i - 1]
        if diff >= 0:
            gains.append(diff)
            losses.append(Decimal(0))
        else:
            gains.append(Decimal(0))
            losses.append(-diff)
    # Wilder smoothing over remaining
    avg_gain = sum(gains) / Decimal(period)
    avg_loss = sum(losses) / Decimal(period)
    for i in range(period + 1, len(values)):
        diff = values[i] - values[i - 1]
        gain = diff if diff > 0 else Decimal(0)
        loss = -diff if diff < 0 else Decimal(0)
        avg_gain = (avg_gain * (Decimal(period) - Decimal(1)) + gain) / Decimal(period)
        avg_loss = (avg_loss * (Decimal(period) - Decimal(1)) + loss) / Decimal(period)
    if avg_loss == 0:
        return Decimal(100)
    rs = avg_gain / avg_loss
    return Decimal(100) - (Decimal(100) / (Decimal(1) + rs))


def macd(values: list[Decimal], fast=12, slow=26, signal=9):
    if len(values) < slow + signal:
        return None, None, None
    ef = ema(values, fast)
    es = ema(values, slow)
    line = [ef[i] - es[i] for i in range(len(values))]
    sig = ema(line, signal)
    hist = [line[i] - sig[i] for i in range(len(values))]
    return line[-1], sig[-1], hist[-1]


def atr(highs, lows, closes, period=14) -> Optional[Decimal]:
    if len(closes) < period + 1:
        return None
    trs = []
    for i in range(1, len(closes)):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
        trs.append(tr)
    if len(trs) < period:
        return None
    # simple average of last period
    return sum(trs[-period:]) / Decimal(period)


def volume_ratio(volumes, period=20) -> Optional[Decimal]:
    if len(volumes) < period + 1:
        return None
    avg = sum(volumes[-period-1:-1]) / Decimal(period)
    if avg == 0:
        return None
    return volumes[-1] / avg