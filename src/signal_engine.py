"""Deterministic signal generation (EMA/RSI) separated from execution."""
from decimal import Decimal
from dataclasses import dataclass
from typing import Optional
import time


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