"""
PHASE 2: OPEN INTEREST (OI) ANALYSIS ENGINE
============================================

PURPOSE:
Analyze Binance Futures Open Interest to determine:
- Trend continuation vs exhaustion
- Short covering vs long liquidation
- Smart money positioning

FORMULAS:

1. OI Trend Strength:
   OI_change_pct = (OI_current - OI_prev) / OI_prev * 100

2. Price-OI Divergence:
   Divergence = sign(Price_change) * sign(OI_change)
   +1 = aligned (continuation)
   -1 = divergence (reversal warning)

3. OI Momentum:
   OI_slope = linear regression slope over 10 periods

4. OI Volatility:
   OI_ATR = ATR of OI series (normalized)

CLASSIFICATION MATRIX:

Price ↑ + OI ↑ = Longs opening (bullish continuation)
Price ↓ + OI ↑ = Shorts opening (bearish continuation)
Price ↑ + OI ↓ = Short covering (bullish exhaustion)
Price ↓ + OI ↓ = Long liquidation (bearish exhaustion)

SCORING:
- OI alignment with trend: +20 to +30
- OI divergence (counter-trend): -20 to -30
- OI spike (>3 std dev): +15
- OI collapse (>3 std dev): -15

OUTPUT:
- OI_SCORE (0-100)
- OI_SIGNAL (ACCUMULATION / DISTRIBUTION / CONTINUATION / EXHAUSTION)
- OI_TREND (RISING / FALLING / FLAT)
"""

import numpy as np
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class OISignal(Enum):
    ACCUMULATION = "ACCUMULATION"
    DISTRIBUTION = "DISTRIBUTION"
    CONTINUATION = "CONTINUATION"
    EXHAUSTION = "EXHAUSTION"
    NEUTRAL = "NEUTRAL"


class OITrend(Enum):
    RISING = "RISING"
    FALLING = "FALLING"
    FLAT = "FLAT"
    SPIKE = "SPIKE"
    COLLAPSE = "COLLAPSE"


@dataclass
class OIResult:
    oi_score: float
    oi_signal: OISignal
    oi_trend: OITrend
    price_oi_correlation: float
    oi_change_pct: float
    oi_momentum: float
    oi_volatility: float
    divergence_strength: float
    smart_money_signal: str
    raw_data: Dict
    
    def to_dict(self) -> Dict:
        return {
            "oi_score": round(self.oi_score, 2),
            "oi_signal": self.oi_signal.value,
            "oi_trend": self.oi_trend.value,
            "price_oi_correlation": round(self.price_oi_correlation, 3),
            "oi_change_pct": round(self.oi_change_pct, 3),
            "oi_momentum": round(self.oi_momentum, 3),
            "oi_volatility": round(self.oi_volatility, 3),
            "divergence_strength": round(self.divergence_strength, 2),
            "smart_money_signal": self.smart_money_signal
        }


class OIAnalyzer:
    """
    Institutional Open Interest Analyzer.
    """
    
    # Thresholds
    OI_CHANGE_SIGNIFICANT = 0.03  # 3% change
    OI_CHANGE_SPIKE = 0.08  # 8% spike
    OI_CHANGE_COLLAPSE = -0.08  # 8% collapse
    DIVERGENCE_THRESHOLD = 0.5
    MOMENTUM_THRESHOLD = 0.02
    
    def __init__(self, lookback: int = 50):
        self.lookback = lookback
    
    def analyze(self, candles: List[Dict], oi_data: List[float]) -> OIResult:
        """
        Analyze OI and price data.
        
        Args:
            candles: OHLCV candles
            oi_data: Open interest values (same length as candles)
            
        Returns:
            OIResult with full analysis
        """
        if len(candles) < 20 or len(oi_data) < 20:
            return OIResult(
                oi_score=50,
                oi_signal=OISignal.NEUTRAL,
                oi_trend=OITrend.FLAT,
                price_oi_correlation=0,
                oi_change_pct=0,
                oi_momentum=0,
                oi_volatility=0,
                divergence_strength=0,
                smart_money_signal="NEUTRAL",
                raw_data={}
            )
        
        prices = np.array([c["close"] for c in candles])
        oi = np.array(oi_data)
        
        # Ensure same length
        min_len = min(len(prices), len(oi))
        prices = prices[-min_len:]
        oi = oi[-min_len:]
        
        # Calculate metrics
        oi_change_pct = self._calculate_oi_change(oi)
        oi_trend = self._classify_oi_trend(oi_change_pct, oi)
        oi_momentum = self._calculate_oi_momentum(oi)
        oi_volatility = self._calculate_oi_volatility(oi)
        
        price_change_pct = (prices[-1] - prices[-5]) / prices[-5] if prices[-5] > 0 else 0
        correlation = self._calculate_correlation(prices[-20:], oi[-20:])
        
        divergence = self._calculate_divergence(price_change_pct, oi_change_pct)
        divergence_strength = abs(divergence)
        
        signal, smart_money = self._classify_signal(
            price_change_pct, oi_change_pct, correlation, divergence
        )
        
        score = self._calculate_oi_score(
            oi_change_pct, oi_trend, correlation, divergence, 
            oi_momentum, oi_volatility
        )
        
        return OIResult(
            oi_score=score,
            oi_signal=signal,
            oi_trend=oi_trend,
            price_oi_correlation=correlation,
            oi_change_pct=oi_change_pct,
            oi_momentum=oi_momentum,
            oi_volatility=oi_volatility,
            divergence_strength=divergence_strength,
            smart_money_signal=smart_money,
            raw_data={
                "prices": prices[-10:].tolist(),
                "oi": oi[-10:].tolist()
            }
        )
    
    def _calculate_oi_change(self, oi: np.ndarray) -> float:
        """OI change percentage over last 5 periods."""
        if len(oi) < 5:
            return 0.0
        return float((oi[-1] - oi[-5]) / oi[-5]) if oi[-5] > 0 else 0.0
    
    def _classify_oi_trend(self, oi_change_pct: float, oi: np.ndarray) -> OITrend:
        """Classify OI trend based on change and volatility."""
        if oi_change_pct > self.OI_CHANGE_SPIKE:
            return OITrend.SPIKE
        elif oi_change_pct < self.OI_CHANGE_COLLAPSE:
            return OITrend.COLLAPSE
        elif oi_change_pct > self.OI_CHANGE_SIGNIFICANT:
            return OITrend.RISING
        elif oi_change_pct < -self.OI_CHANGE_SIGNIFICANT:
            return OITrend.FALLING
        return OITrend.FLAT
    
    def _calculate_oi_momentum(self, oi: np.ndarray, period: int = 10) -> float:
        """Linear regression slope of OI."""
        if len(oi) < period:
            return 0.0
        
        recent = oi[-period:]
        x = np.arange(period)
        
        # Linear regression
        n = period
        sum_x = np.sum(x)
        sum_y = np.sum(recent)
        sum_xy = np.sum(x * recent)
        sum_x2 = np.sum(x * x)
        
        slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x * sum_x)
        
        # Normalize
        mean_oi = np.mean(recent)
        normalized_slope = slope / mean_oi if mean_oi > 0 else 0.0
        
        return float(normalized_slope)
    
    def _calculate_oi_volatility(self, oi: np.ndarray, period: int = 20) -> float:
        """Normalized OI volatility (ATR of OI)."""
        if len(oi) < period + 1:
            return 0.0
        
        recent = oi[-period:]
        
        # Calculate OI ATR
        oi_changes = np.abs(np.diff(recent))
        oi_atr = np.mean(oi_changes)
        
        # Normalize by mean OI
        mean_oi = np.mean(recent)
        normalized_volatility = oi_atr / mean_oi if mean_oi > 0 else 0.0
        
        return float(normalized_volatility)
    
    def _calculate_correlation(self, prices: np.ndarray, oi: np.ndarray) -> float:
        """Pearson correlation between price and OI."""
        if len(prices) < 5 or len(oi) < 5:
            return 0.0
        
        # Ensure same length
        min_len = min(len(prices), len(oi))
        p = prices[-min_len:]
        o = oi[-min_len:]
        
        # Calculate correlation
        p_mean = np.mean(p)
        o_mean = np.mean(o)
        
        numerator = np.sum((p - p_mean) * (o - o_mean))
        denominator = np.sqrt(np.sum((p - p_mean)**2) * np.sum((o - o_mean)**2))
        
        if denominator == 0:
            return 0.0
        
        return float(numerator / denominator)
    
    def _calculate_divergence(self, price_change: float, oi_change: float) -> float:
        """
        Price-OI divergence score.
        
        +1 = strong continuation (aligned)
        -1 = strong divergence (reversal warning)
        """
        if abs(price_change) < 0.001 or abs(oi_change) < 0.001:
            return 0.0
        
        # Sign agreement
        price_sign = np.sign(price_change)
        oi_sign = np.sign(oi_change)
        
        if price_sign == oi_sign:
            # Aligned - continuation
            magnitude = min(abs(price_change) + abs(oi_change), 0.2)
            return magnitude * 5  # 0 to 1
        else:
            # Divergence - exhaustion
            magnitude = min(abs(price_change) + abs(oi_change), 0.2)
            return -magnitude * 5  # -1 to 0
    
    def _classify_signal(self, price_change: float, oi_change: float, 
                         correlation: float, divergence: float) -> Tuple[OISignal, str]:
        """
        Classify OI signal based on price-OI relationship.
        
        Price ↑ + OI ↑ = Longs opening (bullish continuation)
        Price ↓ + OI ↑ = Shorts opening (bearish continuation)
        Price ↑ + OI ↓ = Short covering (bullish exhaustion)
        Price ↓ + OI ↓ = Long liquidation (bearish exhaustion)
        """
        price_up = price_change > 0.001
        price_down = price_change < -0.001
        oi_up = oi_change > self.OI_CHANGE_SIGNIFICANT
        oi_down = oi_change < -self.OI_CHANGE_SIGNIFICANT
        
        if price_up and oi_up:
            return OISignal.CONTINUATION, "LONGS_OPENING"
        elif price_down and oi_up:
            return OISignal.CONTINUATION, "SHORTS_OPENING"
        elif price_up and oi_down:
            return OISignal.EXHAUSTION, "SHORT_COVERING"
        elif price_down and oi_down:
            return OISignal.EXHAUSTION, "LONG_LIQUIDATION"
        
        # Smart money detection
        if abs(correlation) < 0.3 and abs(oi_change) > self.OI_CHANGE_SIGNIFICANT:
            if price_up or oi_up:
                return OISignal.ACCUMULATION, "SM_ACCUMULATION"
            else:
                return OISignal.DISTRIBUTION, "SM_DISTRIBUTION"
        
        return OISignal.NEUTRAL, "NEUTRAL"
    
    def _calculate_oi_score(self, oi_change_pct: float, oi_trend: OITrend,
                           correlation: float, divergence: float,
                           momentum: float, volatility: float) -> float:
        """
        Calculate OI score (0-100).
        
        Higher score = stronger conviction.
        """
        score = 50.0
        
        # Trend strength
        if oi_trend == OITrend.SPIKE:
            score += 25
        elif oi_trend == OITrend.RISING:
            score += 15
        elif oi_trend == OITrend.COLLAPSE:
            score -= 25
        elif oi_trend == OITrend.FALLING:
            score -= 15
        
        # Correlation
        if abs(correlation) > 0.7:
            score += 15  # Strong correlation = conviction
        elif abs(correlation) < 0.3:
            score -= 10  # Weak correlation = uncertainty
        
        # Divergence
        if divergence > 0.5:
            score += 15
        elif divergence < -0.5:
            score -= 15
        
        # Momentum
        if abs(momentum) > self.MOMENTUM_THRESHOLD:
            score += 10
        
        # Volatility penalty
        if volatility > 0.05:
            score -= 10
        
        return max(0, min(100, score))
    
    def get_directional_bias(self, result: OIResult) -> str:
        """
        Get directional bias from OI analysis.
        """
        if result.oi_signal == OISignal.CONTINUATION:
            if result.oi_change_pct > 0:
                return "BULLISH" if result.price_oi_correlation > 0 else "BEARISH"
            return "NEUTRAL"
        
        if result.oi_signal == OISignal.ACCUMULATION:
            return "BULLISH"
        
        if result.oi_signal == OISignal.DISTRIBUTION:
            return "BEARISH"
        
        return "NEUTRAL"


# Global instance
_oi_analyzer = None

def get_analyzer() -> OIAnalyzer:
    global _oi_analyzer
    if _oi_analyzer is None:
        _oi_analyzer = OIAnalyzer()
    return _oi_analyzer


def analyze_oi(candles: List[Dict], oi_data: List[float]) -> Dict:
    """
    Convenience function for external modules.
    """
    analyzer = get_analyzer()
    result = analyzer.analyze(candles, oi_data)
    return result.to_dict()
