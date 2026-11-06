"""Deterministic signal generation (EMA/RSI) separated from execution."""
from decimal import Decimal
from dataclasses import dataclass
from typing import Optional
import time
from . import indicators as ind

@dataclass
class Signal:
    symbol: str
    direction: str
    timestamp: int
    timeframe: str
    entry_price: Decimal
    stop_loss: Decimal
    take_profit: Decimal
    confidence: float
    gross_rr: Decimal
    net_rr: Decimal
    invalidation: str
    rsi_value: Decimal = Decimal("0")
    ema_fast: Decimal = Decimal("0")
    ema_slow: Decimal = Decimal("0")
    ema_50: Decimal = Decimal("0")
    macd: Decimal = Decimal("0")
    atr: Decimal = Decimal("0")
    volume_ratio: Decimal = Decimal("0")
    score: float = 0.0
    explanation: str = ""
    candle_close_time: int = 0

    @property
    def signal_id(self) -> str:
        return f"{self.symbol}:{self.timeframe}:{self.candle_close_time}:{self.direction}"


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
    avg_gain = sum(gains) / Decimal(period)
    avg_loss = sum(losses) / Decimal(period)
    if avg_loss == 0:
        return Decimal(100)
    rs = avg_gain / avg_loss
    return Decimal(100) - (Decimal(100) / (Decimal(1) + rs))


class SignalEngine:
    # Initial test parameters, not validated profitable thresholds.
    RSI_LONG_MIN = Decimal("50")
    RSI_LONG_MAX = Decimal("70")
    RSI_SHORT_MIN = Decimal("30")
    RSI_SHORT_MAX = Decimal("50")
    WARMUP = 50

    def __init__(self, cooldown_seconds: int = 3600,
                 rsi_long_min: Decimal = RSI_LONG_MIN,
                 rsi_long_max: Decimal = RSI_LONG_MAX,
                 rsi_short_min: Decimal = RSI_SHORT_MIN,
                 rsi_short_max: Decimal = RSI_SHORT_MAX):
        self.cooldown_seconds = cooldown_seconds
        self.rsi_long_min = rsi_long_min
        self.rsi_long_max = rsi_long_max
        self.rsi_short_min = rsi_short_min
        self.rsi_short_max = rsi_short_max
        self._last_signal_ts: dict[str, int] = {}
        self._seen_ids: set[str] = set()

    def evaluate(self, symbol: str, timeframe: str, closes: list[Decimal],
                candle_close_time: int = 0) -> Optional[Signal]:
        if len(closes) < self.WARMUP:
            return None
        fast = ema(closes, 9)
        slow = ema(closes, 21)
        r = rsi(closes, 14)
        if r is None:
            return None
        last_fast = fast[-1]
        prev_fast = fast[-2]
        last_slow = slow[-1]
        prev_slow = slow[-2]

        direction = None
        if prev_fast <= prev_slow and last_fast > last_slow and self.rsi_long_min <= r <= self.rsi_long_max:
            direction = "LONG"
        elif prev_fast >= prev_slow and last_fast < last_slow and self.rsi_short_min <= r <= self.rsi_short_max:
            direction = "SHORT"

        if direction is None:
            return None

        now = int(time.time())
        last = self._last_signal_ts.get(symbol, 0)
        if now - last < self.cooldown_seconds:
            return None

        entry = closes[-1]
        recent = closes[-14:]
        hi = max(recent)
        lo = min(recent)
        atr_approx = (hi - lo) / Decimal(2)
        if atr_approx <= 0:
            atr_approx = entry * Decimal("0.005")

        if direction == "LONG":
            stop = entry - (atr_approx * Decimal("1.5"))
            tp = entry + (atr_approx * Decimal("3.0"))
        else:
            stop = entry + (atr_approx * Decimal("1.5"))
            tp = entry - (atr_approx * Decimal("3.0"))

        gross_rr = abs(tp - entry) / abs(entry - stop) if abs(entry - stop) > 0 else Decimal(0)
        net_rr = gross_rr

        cct = candle_close_time or int(time.time())
        sig = Signal(
            symbol=symbol,
            direction=direction,
            timestamp=now,
            timeframe=timeframe,
            entry_price=entry,
            stop_loss=stop,
            take_profit=tp,
            confidence=float(r) / 100.0,
            gross_rr=gross_rr,
            net_rr=net_rr,
            invalidation="EMA cross reversal or RSI extreme",
            rsi_value=r,
            ema_fast=last_fast,
            ema_slow=last_slow,
            candle_close_time=cct,
        )
        if sig.signal_id in self._seen_ids:
            return None
        self._seen_ids.add(sig.signal_id)
        self._last_signal_ts[symbol] = now
        return sig

    def evaluate_klines(self, symbol: str, timeframe: str, klines: list, candle_close_time: int = 0) -> Optional[Signal]:
        # Use completed candles only (exclude last potentially open candle)
        if not klines or len(klines) < 60:
            return None
        completed = klines[:-1]
        if len(completed) < 50:
            return None
        closes = [Decimal(str(k[4])) for k in completed]
        highs = [Decimal(str(k[2])) for k in completed]
        lows = [Decimal(str(k[3])) for k in completed]
        volumes = [Decimal(str(k[5])) for k in completed]

        fast_ema = ind.ema(closes, 9)
        slow_ema = ind.ema(closes, 21)
        ema50 = ind.ema(closes, 50)
        r = ind.rsi(closes, 14)
        macd_line, macd_sig, macd_hist = ind.macd(closes)
        atr_val = ind.atr(highs, lows, closes, 14)
        vr = ind.volume_ratio(volumes, 20)

        if r is None or atr_val is None or macd_hist is None:
            return None

        last_fast = fast_ema[-1]
        prev_fast = fast_ema[-2]
        last_slow = slow_ema[-1]
        prev_slow = slow_ema[-2]
        last_ema50 = ema50[-1]

        now = int(time.time())
        last = self._last_signal_ts.get(symbol, 0)
        if now - last < self.cooldown_seconds:
            return None

        direction = None
        score = 0.0
        reasons = []
        # LONG conditions
        long_cond = (
            last_fast > last_slow and last_slow > last_ema50 and
            prev_fast <= prev_slow and
            Decimal("40") <= r <= Decimal("70") and
            macd_hist > 0 and
            (vr is not None and vr >= Decimal("1.2"))
        )
        short_cond = (
            last_fast < last_slow and last_slow < last_ema50 and
            prev_fast >= prev_slow and
            Decimal("30") <= r <= Decimal("60") and
            macd_hist < 0 and
            (vr is not None and vr >= Decimal("1.2"))
        )
        if long_cond:
            direction = "LONG"
            score = 70.0
            reasons.append("EMA9>EMA21>EMA50")
            reasons.append("RSI in range")
            reasons.append("MACD hist positive")
            reasons.append("volume spike")
        elif short_cond:
            direction = "SHORT"
            score = 70.0
            reasons.append("EMA9<EMA21<EMA50")
            reasons.append("RSI in range")
            reasons.append("MACD hist negative")
            reasons.append("volume spike")
        else:
            return None

        entry = closes[-1]
        atr = atr_val
        if direction == "LONG":
            stop = entry - (atr * Decimal("1.5"))
            tp = entry + (atr * Decimal("3.0"))
        else:
            stop = entry + (atr * Decimal("1.5"))
            tp = entry - (atr * Decimal("3.0"))

        gross_rr = abs(tp - entry) / abs(entry - stop) if abs(entry - stop) > 0 else Decimal(0)

        cct = candle_close_time or int(completed[-1][0]) + 0
        if cct == 0:
            cct = int(time.time())
        sig = Signal(
            symbol=symbol,
            direction=direction,
            timestamp=now,
            timeframe=timeframe,
            entry_price=entry,
            stop_loss=stop,
            take_profit=tp,
            confidence=float(r) / 100.0,
            gross_rr=gross_rr,
            net_rr=gross_rr,
            invalidation="EMA cross reversal or RSI extreme",
            rsi_value=r,
            ema_fast=last_fast,
            ema_slow=last_slow,
            ema_50=last_ema50,
            macd=macd_hist,
            atr=atr,
            volume_ratio=vr if vr is not None else Decimal(0),
            score=score,
            explanation="; ".join(reasons),
            candle_close_time=cct,
        )
        if sig.signal_id in self._seen_ids:
            return None
        self._seen_ids.add(sig.signal_id)
        self._last_signal_ts[symbol] = now
        return sig