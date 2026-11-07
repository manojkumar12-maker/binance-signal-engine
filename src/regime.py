"""Market regime classification.

Classifies market state from closed-candle indicators so the signal engine
can select an appropriate strategy (or stand aside). All inputs must be
computed on completed candles only to avoid look-ahead bias.
"""
from decimal import Decimal
from dataclasses import dataclass, field
from typing import Optional

from . import indicators as ind


REGIMES = (
    "STRONG_UPTREND",
    "WEAK_UPTREND",
    "STRONG_DOWNTREND",
    "WEAK_DOWNTREND",
    "SIDEWAYS",
    "HIGH_VOLATILITY",
    "LOW_LIQUIDITY",
    "UNKNOWN",
)


@dataclass
class RegimeResult:
    regime: str = "UNKNOWN"
    reasons: list = field(default_factory=list)
    adx: Optional[Decimal] = None
    atr_pct: Optional[Decimal] = None
    ema21_slope: Optional[Decimal] = None
    price_vs_ema50: Optional[str] = None
    price_vs_ema200: Optional[str] = None
    trend_direction: str = "NONE"  # UP | DOWN | NONE
    tradeable: bool = False

    def to_dict(self):
        return {
            "regime": self.regime,
            "reasons": list(self.reasons),
            "adx": str(self.adx) if self.adx is not None else None,
            "atr_pct": str(self.atr_pct) if self.atr_pct is not None else None,
            "ema21_slope": str(self.ema21_slope) if self.ema21_slope is not None else None,
            "price_vs_ema50": self.price_vs_ema50,
            "price_vs_ema200": self.price_vs_ema200,
            "trend_direction": self.trend_direction,
            "tradeable": self.tradeable,
        }


class RegimeClassifier:
    def __init__(self, adx_trend: Decimal = Decimal("25"), adx_strong: Decimal = Decimal("30"),
                 atr_pct_high: Decimal = Decimal("5.0"), atr_pct_low_liq: Decimal = Decimal("0.05"),
                 min_avg_volume: Decimal = Decimal("0")):
        self.adx_trend = adx_trend
        self.adx_strong = adx_strong
        self.atr_pct_high = atr_pct_high
        self.atr_pct_low_liq = atr_pct_low_liq
        self.min_avg_volume = min_avg_volume

    def classify(self, highs, lows, closes, volumes) -> RegimeResult:
        r = RegimeResult()
        if not closes or len(closes) < 60:
            r.reasons.append("insufficient history")
            return r

        price = closes[-1]
        ema21 = ind.ema(closes, 21)
        ema50 = ind.ema(closes, 50)
        ema200 = ind.ema(closes, 200) if len(closes) >= 200 else None
        adx_val = ind.adx(highs, lows, closes, 14)
        atr_val = ind.atr_wilder(highs, lows, closes, 14)
        atr_pct = ind.atr_percent(atr_val, price)
        slope = ind.ema_slope(ema21, 5)
        avg_vol = ind.volume_sma(volumes, 20)

        r.adx = adx_val
        r.atr_pct = atr_pct
        r.ema21_slope = slope
        r.price_vs_ema50 = "ABOVE" if price > ema50[-1] else "BELOW"
        if ema200:
            r.price_vs_ema200 = "ABOVE" if price > ema200[-1] else "BELOW"

        if avg_vol is not None and self.min_avg_volume > 0 and avg_vol < self.min_avg_volume:
            r.regime = "LOW_LIQUIDITY"
            r.reasons.append(f"avg volume {avg_vol} below minimum {self.min_avg_volume}")
            return r

        if atr_pct is not None and atr_pct > self.atr_pct_high:
            r.regime = "HIGH_VOLATILITY"
            r.reasons.append(f"ATR% {atr_pct:.2f} above limit {self.atr_pct_high}")
            return r

        ema9 = ind.ema(closes, 9)
        bull_align = ema9[-1] > ema21[-1] > ema50[-1]
        bear_align = ema9[-1] < ema21[-1] < ema50[-1]
        slope_up = slope is not None and slope > 0
        slope_down = slope is not None and slope < 0
        adx_trending = adx_val is not None and adx_val >= self.adx_trend
        adx_strong = adx_val is not None and adx_val >= self.adx_strong

        if bull_align and slope_up:
            r.trend_direction = "UP"
            if adx_strong:
                r.regime = "STRONG_UPTREND"
                r.reasons.append("EMA bull alignment + rising slope + strong ADX")
            else:
                r.regime = "WEAK_UPTREND"
                r.reasons.append("EMA bull alignment + rising slope, weak ADX")
            r.tradeable = True
        elif bear_align and slope_down:
            r.trend_direction = "DOWN"
            if adx_strong:
                r.regime = "STRONG_DOWNTREND"
                r.reasons.append("EMA bear alignment + falling slope + strong ADX")
            else:
                r.regime = "WEAK_DOWNTREND"
                r.reasons.append("EMA bear alignment + falling slope, weak ADX")
            r.tradeable = True
        elif not adx_trending and atr_pct is not None:
            r.regime = "SIDEWAYS"
            r.reasons.append(f"ADX {adx_val} below {self.adx_trend}, no EMA alignment")
        else:
            r.regime = "UNKNOWN"
            r.reasons.append("mixed signals")
        return r
