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


def volume_sma(volumes, period=20) -> Optional[Decimal]:
    if len(volumes) < period:
        return None
    return sum(volumes[-period:]) / Decimal(period)


def atr_wilder(highs, lows, closes, period=14) -> Optional[Decimal]:
    if len(closes) < period + 1:
        return None
    trs = []
    for i in range(1, len(closes)):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
        trs.append(tr)
    if len(trs) < period:
        return None
    a = sum(trs[:period]) / Decimal(period)
    for tr in trs[period:]:
        a = (a * (Decimal(period) - Decimal(1)) + tr) / Decimal(period)
    return a


def atr_percent(atr_value, price) -> Optional[Decimal]:
    if atr_value is None or price is None or price == 0:
        return None
    return (atr_value / price) * Decimal(100)


def ema_slope(values: list[Decimal], lookback: int = 5) -> Optional[Decimal]:
    if not values or len(values) < lookback + 1:
        return None
    prev = values[-lookback - 1]
    if prev == 0:
        return None
    return ((values[-1] - prev) / prev) * Decimal(100)


def vwap(highs, lows, closes, volumes) -> Optional[Decimal]:
    if not closes or len(closes) != len(volumes) or not volumes:
        return None
    pv = Decimal(0)
    vv = Decimal(0)
    for i in range(len(closes)):
        typical = (highs[i] + lows[i] + closes[i]) / Decimal(3)
        pv += typical * volumes[i]
        vv += volumes[i]
    if vv == 0:
        return None
    return pv / vv


def rolling_vwap(highs, lows, closes, volumes, period=48) -> Optional[Decimal]:
    if len(closes) < period:
        return None
    return vwap(highs[-period:], lows[-period:], closes[-period:], volumes[-period:])


def adx(highs, lows, closes, period=14) -> Optional[Decimal]:
    n = len(closes)
    if n < period * 2 + 1:
        return None
    plus_dm, minus_dm, trs = [], [], []
    for i in range(1, n):
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        plus_dm.append(up if (up > down and up > 0) else Decimal(0))
        minus_dm.append(down if (down > up and down > 0) else Decimal(0))
        trs.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))

    def wilder_smooth(vals, p):
        if len(vals) < p:
            return None
        s = sum(vals[:p])
        out = [s]
        for v in vals[p:]:
            s = s - (s / Decimal(p)) + v
            out.append(s)
        return out

    tr_s = wilder_smooth(trs, period)
    pdm_s = wilder_smooth(plus_dm, period)
    mdm_s = wilder_smooth(minus_dm, period)
    if not tr_s or not pdm_s or not mdm_s:
        return None
    dxs = []
    for i in range(len(tr_s)):
        if tr_s[i] == 0:
            continue
        pdi = (pdm_s[i] / tr_s[i]) * Decimal(100)
        mdi = (mdm_s[i] / tr_s[i]) * Decimal(100)
        denom = pdi + mdi
        if denom == 0:
            continue
        dxs.append(abs(pdi - mdi) / denom * Decimal(100))
    if len(dxs) < period:
        return None
    adx_val = sum(dxs[:period]) / Decimal(period)
    for d in dxs[period:]:
        adx_val = (adx_val * (Decimal(period) - Decimal(1)) + d) / Decimal(period)
    return adx_val


def bollinger_bands(closes, period=20, mult=Decimal("2.0")):
    mult = Decimal(str(mult))
    if len(closes) < period:
        return None, None, None
    window = closes[-period:]
    mid = sum(window) / Decimal(period)
    var = sum((c - mid) ** 2 for c in window) / Decimal(period)
    sd = var.sqrt()
    return mid + mult * sd, mid, mid - mult * sd


def bb_percent_b(closes, period=20, mult=Decimal("2.0")) -> Optional[Decimal]:
    upper, mid, lower = bollinger_bands(closes, period, mult)
    if upper is None or lower is None or upper == lower:
        return None
    return (closes[-1] - lower) / (upper - lower)


def swing_levels(highs, lows, left=3, right=3, max_levels=3):
    n = len(highs)
    if n < left + right + 1:
        return [], []
    res, sup = [], []
    for i in range(left, n - right):
        wh = highs[i - left:i + right + 1]
        wl = lows[i - left:i + right + 1]
        if highs[i] == max(wh):
            res.append((i, highs[i]))
        if lows[i] == min(wl):
            sup.append((i, lows[i]))
    return [p for _, p in res[-max_levels:]], [p for _, p in sup[-max_levels:]]


def nearest_level(levels, price, direction="above") -> Optional[Decimal]:
    if not levels:
        return None
    if direction == "above":
        cands = [l for l in levels if l < price]
        return max(cands) if cands else None
    cands = [l for l in levels if l > price]
    return min(cands) if cands else None