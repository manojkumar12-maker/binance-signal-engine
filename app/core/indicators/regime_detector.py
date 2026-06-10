"""
PHASE 1: INSTITUTIONAL MARKET REGIME DETECTION ENGINE
======================================================

PURPOSE:
Classifies every asset into one of six market regimes using 
multi-factor quantitative analysis.

REGIMES:
- TRENDING_BULL: Strong directional upward movement
- TRENDING_BEAR: Strong directional downward movement  
- RANGING: Sideways chop, no clear direction
- VOLATILE: High volatility, unpredictable direction
- ACCUMULATION: Smart money silently accumulating
- DISTRIBUTION: Smart money distributing positions

FACTORS:
- ADX (Average Directional Index)
- ATR (Average True Range)
- EMA Slope (trend direction/strength)
- Volume Profile (abnormal volume patterns)
- Price Structure (higher highs/lows vs chop)
- Bollinger Band Width (volatility regime)

THRESHOLDS:
- ADX > 25 = Trending, < 20 = Ranging
- ATR_ratio > 0.015 = Volatile, < 0.003 = Compressed
- EMA_slope > 0.001 = Bullish, < -0.001 = Bearish
- Volume_zscore > 2.5 = Abnormal
- BB_width > 0.08 = Volatile, < 0.02 = Compressed

OPTIMIZATION:
- Cached rolling calculations
- NumPy vectorized math
- 100-period lookback default
"""

import numpy as np
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class MarketRegime(Enum):
    TRENDING_BULL = "TRENDING_BULL"
    TRENDING_BEAR = "TRENDING_BEAR"
    RANGING = "RANGING"
    VOLATILE = "VOLATILE"
    ACCUMULATION = "ACCUMULATION"
    DISTRIBUTION = "DISTRIBUTION"
    UNKNOWN = "UNKNOWN"


@dataclass
class RegimeResult:
    regime: MarketRegime
    adx: float
    atr_ratio: float
    ema_slope: float
    bb_width: float
    volume_zscore: float
    price_structure: float
    trend_strength: float
    confidence: float
    raw_scores: Dict[str, float]
    
    def to_dict(self) -> Dict:
        return {
            "regime": self.regime.value,
            "adx": round(self.adx, 2),
            "atr_ratio": round(self.atr_ratio, 6),
            "ema_slope": round(self.ema_slope, 6),
            "bb_width": round(self.bb_width, 4),
            "volume_zscore": round(self.volume_zscore, 2),
            "price_structure": round(self.price_structure, 2),
            "trend_strength": round(self.trend_strength, 2),
            "confidence": round(self.confidence, 2),
            "raw_scores": {k: round(v, 2) for k, v in self.raw_scores.items()}
        }


class RegimeDetector:
    """
    Institutional-grade market regime classifier.
    Uses multi-factor scoring with adaptive thresholds.
    """
    
    # Thresholds
    ADX_TRENDING = 25.0
    ADX_RANGING = 20.0
    ATR_VOLATILE = 0.015
    ATR_COMPRESSED = 0.003
    EMA_SLOPE_BULL = 0.001
    EMA_SLOPE_BEAR = -0.001
    BB_WIDTH_VOLATILE = 0.08
    BB_WIDTH_COMPRESSED = 0.02
    VOLUME_ZSCORE_ABNORMAL = 2.5
    VOLUME_ZSCORE_LOW = 0.5
    
    def __init__(self, lookback: int = 100):
        self.lookback = lookback
        
    def detect(self, candles: List[Dict]) -> RegimeResult:
        """
        Main entry point: analyze candles and return regime classification.
        
        Args:
            candles: List of OHLCV dicts with keys: open, high, low, close, volume
            
        Returns:
            RegimeResult with full classification and scores
        """
        if len(candles) < 50:
            return RegimeResult(
                regime=MarketRegime.UNKNOWN,
                adx=0, atr_ratio=0, ema_slope=0, bb_width=0,
                volume_zscore=0, price_structure=0, trend_strength=0,
                confidence=0, raw_scores={}
            )
        
        closes = np.array([c["close"] for c in candles])
        highs = np.array([c["high"] for c in candles])
        lows = np.array([c["low"] for c in candles])
        volumes = np.array([c.get("volume", 0) for c in candles])
        
        # Calculate indicators
        adx = self._calculate_adx(highs, lows, closes, period=14)
        atr_ratio = self._calculate_atr_ratio(highs, lows, closes)
        ema_slope = self._calculate_ema_slope(closes, period=50)
        bb_width = self._calculate_bb_width(closes, period=20)
        volume_zscore = self._calculate_volume_zscore(volumes)
        price_structure = self._calculate_price_structure(highs, lows, closes)
        
        # Classify regime
        regime, confidence, raw_scores = self._classify_regime(
            adx, atr_ratio, ema_slope, bb_width, volume_zscore, price_structure
        )
        
        trend_strength = self._calculate_trend_strength(adx, ema_slope, price_structure)
        
        return RegimeResult(
            regime=regime,
            adx=adx,
            atr_ratio=atr_ratio,
            ema_slope=ema_slope,
            bb_width=bb_width,
            volume_zscore=volume_zscore,
            price_structure=price_structure,
            trend_strength=trend_strength,
            confidence=confidence,
            raw_scores=raw_scores
        )
    
    def _calculate_adx(self, highs: np.ndarray, lows: np.ndarray, 
                       closes: np.ndarray, period: int = 14) -> float:
        """
        Calculate Average Directional Index (ADX).
        
        Formula:
        TR = max(high - low, |high - prev_close|, |low - prev_close|)
        +DM = high - prev_high (if positive and > -DM)
        -DM = prev_low - low (if positive and > +DM)
        DX = 100 * |+DI - -DI| / |+DI + -DI|
        ADX = EMA(DX, period)
        """
        if len(highs) < period + 2:
            return 0.0
        
        tr1 = highs[1:] - lows[1:]
        tr2 = np.abs(highs[1:] - closes[:-1])
        tr3 = np.abs(lows[1:] - closes[:-1])
        tr = np.maximum(np.maximum(tr1, tr2), tr3)
        
        plus_dm = highs[1:] - highs[:-1]
        minus_dm = lows[:-1] - lows[1:]
        
        plus_dm = np.where((plus_dm > minus_dm) & (plus_dm > 0), plus_dm, 0)
        minus_dm = np.where((minus_dm > plus_dm) & (minus_dm > 0), minus_dm, 0)
        
        atr = np.convolve(tr, np.ones(period)/period, mode='valid')
        plus_di = 100 * np.convolve(plus_dm, np.ones(period)/period, mode='valid') / (atr + 1e-10)
        minus_di = 100 * np.convolve(minus_dm, np.ones(period)/period, mode='valid') / (atr + 1e-10)
        
        dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10)
        
        if len(dx) < period:
            return 0.0
        
        adx = np.mean(dx[-period:])
        return float(adx)
    
    def _calculate_atr_ratio(self, highs: np.ndarray, lows: np.ndarray, 
                             closes: np.ndarray, period: int = 14) -> float:
        """
        Calculate ATR as ratio of current price.
        
        Formula: ATR / close[-1]
        """
        if len(highs) < period + 1:
            return 0.0
        
        tr1 = highs[1:] - lows[1:]
        tr2 = np.abs(highs[1:] - closes[:-1])
        tr3 = np.abs(lows[1:] - closes[:-1])
        tr = np.maximum(np.maximum(tr1, tr2), tr3)
        
        atr = np.mean(tr[-period:])
        return float(atr / closes[-1]) if closes[-1] > 0 else 0.0
    
    def _calculate_ema_slope(self, closes: np.ndarray, period: int = 50) -> float:
        """
        Calculate slope of EMA as trend direction.
        
        Formula: (EMA_now - EMA_10_periods_ago) / EMA_now
        """
        if len(closes) < period + 10:
            return 0.0
        
        ema = self._ema(closes, period)
        if len(ema) < 10:
            return 0.0
        
        slope = (ema[-1] - ema[-10]) / ema[-1] if ema[-1] > 0 else 0.0
        return float(slope)
    
    def _calculate_bb_width(self, closes: np.ndarray, period: int = 20) -> float:
        """
        Calculate Bollinger Band width as volatility measure.
        
        Formula: (upper - lower) / middle
        """
        if len(closes) < period:
            return 0.0
        
        sma = np.mean(closes[-period:])
        std = np.std(closes[-period:])
        
        upper = sma + 2 * std
        lower = sma - 2 * std
        
        width = (upper - lower) / sma if sma > 0 else 0.0
        return float(width)
    
    def _calculate_volume_zscore(self, volumes: np.ndarray, period: int = 20) -> float:
        """
        Calculate volume z-score for anomaly detection.
        
        Formula: (volume - mean) / std
        """
        if len(volumes) < period + 1:
            return 0.0
        
        recent = volumes[-period:]
        mean = np.mean(recent)
        std = np.std(recent)
        
        if std == 0:
            return 0.0
        
        zscore = (volumes[-1] - mean) / std
        return float(zscore)
    
    def _calculate_price_structure(self, highs: np.ndarray, lows: np.ndarray, 
                                    closes: np.ndarray, lookback: int = 20) -> float:
        """
        Calculate price structure score.
        
        +1 for each higher high
        -1 for each lower high
        +1 for each higher low
        -1 for each lower low
        
        Normalized to -1 to 1 range.
        """
        if len(highs) < lookback + 2:
            return 0.0
        
        h = highs[-lookback:]
        l = lows[-lookback:]
        
        hh = 0
        lh = 0
        hl = 0
        ll = 0
        
        for i in range(1, len(h)):
            if h[i] > h[i-1]:
                hh += 1
            else:
                lh += 1
            
            if l[i] > l[i-1]:
                hl += 1
            else:
                ll += 1
        
        total = hh + lh + hl + ll
        if total == 0:
            return 0.0
        
        score = (hh + hl - lh - ll) / total
        return float(score)
    
    def _calculate_trend_strength(self, adx: float, ema_slope: float, 
                                   price_structure: float) -> float:
        """
        Composite trend strength score (0-1).
        """
        adx_score = min(adx / 50.0, 1.0)
        slope_score = min(abs(ema_slope) / 0.005, 1.0)
        structure_score = abs(price_structure)
        
        return float((adx_score * 0.4 + slope_score * 0.3 + structure_score * 0.3))
    
    def _classify_regime(self, adx: float, atr_ratio: float, ema_slope: float,
                         bb_width: float, volume_zscore: float, 
                         price_structure: float) -> Tuple[MarketRegime, float, Dict]:
        """
        Multi-factor regime classification with confidence scoring.
        """
        scores = {
            "trending_bull": 0.0,
            "trending_bear": 0.0,
            "ranging": 0.0,
            "volatile": 0.0,
            "accumulation": 0.0,
            "distribution": 0.0
        }
        
        # ADX scoring
        if adx > self.ADX_TRENDING:
            if ema_slope > 0:
                scores["trending_bull"] += 30
                scores["accumulation"] += 10
            else:
                scores["trending_bear"] += 30
                scores["distribution"] += 10
        elif adx < self.ADX_RANGING:
            scores["ranging"] += 25
            if volume_zscore > self.VOLUME_ZSCORE_ABNORMAL:
                if ema_slope > 0:
                    scores["accumulation"] += 20
                else:
                    scores["distribution"] += 20
        
        # Volatility scoring
        if atr_ratio > self.ATR_VOLATILE or bb_width > self.BB_WIDTH_VOLATILE:
            scores["volatile"] += 35
        elif atr_ratio < self.ATR_COMPRESSED and bb_width < self.BB_WIDTH_COMPRESSED:
            scores["ranging"] += 20
        
        # EMA slope scoring
        if ema_slope > self.EMA_SLOPE_BULL:
            scores["trending_bull"] += 20
        elif ema_slope < self.EMA_SLOPE_BEAR:
            scores["trending_bear"] += 20
        else:
            scores["ranging"] += 15
        
        # Price structure scoring
        if price_structure > 0.3:
            scores["trending_bull"] += 15
        elif price_structure < -0.3:
            scores["trending_bear"] += 15
        else:
            scores["ranging"] += 10
        
        # Volume scoring
        if volume_zscore > self.VOLUME_ZSCORE_ABNORMAL:
            if ema_slope > 0:
                scores["accumulation"] += 15
            else:
                scores["distribution"] += 15
        elif volume_zscore < self.VOLUME_ZSCORE_LOW:
            scores["ranging"] += 10
        
        # Smart money detection: low volatility + high volume = accumulation/distribution
        if atr_ratio < self.ATR_COMPRESSED and volume_zscore > self.VOLUME_ZSCORE_ABNORMAL:
            if ema_slope > 0:
                scores["accumulation"] += 25
            else:
                scores["distribution"] += 25
        
        # Determine winner
        regime = max(scores.items(), key=lambda x: x[1])[0]
        confidence = scores[regime]
        
        # Normalize confidence to 0-100
        total_score = sum(scores.values())
        if total_score > 0:
            confidence = (confidence / total_score) * 100
        
        regime_map = {
            "trending_bull": MarketRegime.TRENDING_BULL,
            "trending_bear": MarketRegime.TRENDING_BEAR,
            "ranging": MarketRegime.RANGING,
            "volatile": MarketRegime.VOLATILE,
            "accumulation": MarketRegime.ACCUMULATION,
            "distribution": MarketRegime.DISTRIBUTION
        }
        
        return regime_map[regime], confidence, scores
    
    def _ema(self, data: np.ndarray, period: int) -> np.ndarray:
        """Calculate exponential moving average."""
        alpha = 2.0 / (period + 1)
        ema = np.zeros_like(data)
        ema[0] = data[0]
        
        for i in range(1, len(data)):
            ema[i] = alpha * data[i] + (1 - alpha) * ema[i-1]
        
        return ema
    
    def is_tradeable(self, result: RegimeResult) -> Tuple[bool, str]:
        """
        Determine if a regime allows trading.
        
        Returns:
            (is_tradeable, reason)
        """
        if result.regime == MarketRegime.RANGING:
            return False, "Ranging market - no directional bias"
        
        if result.regime == MarketRegime.VOLATILE:
            return False, "Volatile market - avoid unpredictable moves"
        
        if result.regime == MarketRegime.UNKNOWN:
            return False, "Insufficient data"
        
        if result.confidence < 60:
            return False, f"Low regime confidence ({result.confidence:.1f})"
        
        return True, "OK"


# Global instance for caching
_regime_detector = None

def get_detector() -> RegimeDetector:
    global _regime_detector
    if _regime_detector is None:
        _regime_detector = RegimeDetector()
    return _regime_detector


def detect_regime(candles: List[Dict]) -> Dict:
    """
    Convenience function for external modules.
    """
    detector = get_detector()
    result = detector.detect(candles)
    return result.to_dict()
