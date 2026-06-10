"""
PHASE 4: WHALE DETECTION ENGINE
================================

PURPOSE:
Detect institutional/whale activity through:
- Volume anomaly detection
- Order flow analysis
- CVD (Cumulative Volume Delta) divergence
- Large wick absorption
- Hidden accumulation/distribution

OUTPUT:
- WHALE_SCORE (0-100)
- WHALE_SIGNAL (ACCUMULATION / DISTRIBUTION / AGGRESSIVE_BUY / AGGRESSIVE_SELL / NEUTRAL)

DETECTION LOGIC:
1. Volume spike > 3 sigma = whale activity
2. Large body candle + high volume = aggressive move
3. Wick absorption (large wick, close near open) = hidden orders
4. CVD divergence = smart money positioning
5. OI spike + volume = institutional positioning

THRESHOLDS:
- Volume z-score > 3.0 = whale volume
- Body/range ratio > 0.8 = aggressive
- Wick absorption > 0.6 = hidden orders
- CVD divergence > 0.5 = smart money
"""

import numpy as np
from typing import List, Dict, Tuple
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class WhaleSignal(Enum):
    ACCUMULATION = "ACCUMULATION"
    DISTRIBUTION = "DISTRIBUTION"
    AGGRESSIVE_BUY = "AGGRESSIVE_BUY"
    AGGRESSIVE_SELL = "AGGRESSIVE_SELL"
    HIDDEN_ACCUMULATION = "HIDDEN_ACCUMULATION"
    HIDDEN_DISTRIBUTION = "HIDDEN_DISTRIBUTION"
    NEUTRAL = "NEUTRAL"


@dataclass
class WhaleResult:
    whale_signal: WhaleSignal
    whale_score: float
    volume_zscore: float
    cvd_divergence: float
    absorption_ratio: float
    aggressive_ratio: float
    oi_correlation: float
    smart_money_detected: bool
    
    def to_dict(self) -> Dict:
        return {
            "whale_signal": self.whale_signal.value,
            "whale_score": round(self.whale_score, 2),
            "volume_zscore": round(self.volume_zscore, 2),
            "cvd_divergence": round(self.cvd_divergence, 2),
            "absorption_ratio": round(self.absorption_ratio, 2),
            "aggressive_ratio": round(self.aggressive_ratio, 2),
            "oi_correlation": round(self.oi_correlation, 2),
            "smart_money_detected": self.smart_money_detected
        }


class WhaleDetector:
    """
    Detect whale and smart money activity.
    """
    
    VOLUME_ZSCORE_THRESHOLD = 3.0
    AGGRESSIVE_THRESHOLD = 0.8
    ABSORPTION_THRESHOLD = 0.6
    CVD_DIVERGENCE_THRESHOLD = 0.5
    
    def detect(self, candles: List[Dict], oi_data: List[float] = None) -> WhaleResult:
        if len(candles) < 20:
            return WhaleResult(
                whale_signal=WhaleSignal.NEUTRAL,
                whale_score=0,
                volume_zscore=0,
                cvd_divergence=0,
                absorption_ratio=0,
                aggressive_ratio=0,
                oi_correlation=0,
                smart_money_detected=False
            )
        
        # Calculate metrics
        volume_zscore = self._calculate_volume_zscore(candles)
        cvd_divergence = self._calculate_cvd_divergence(candles)
        absorption_ratio = self._calculate_absorption(candles)
        aggressive_ratio = self._calculate_aggressive_ratio(candles)
        oi_correlation = self._calculate_oi_correlation(candles, oi_data or [])
        
        # Classify
        signal, score = self._classify(
            volume_zscore, cvd_divergence, absorption_ratio,
            aggressive_ratio, oi_correlation
        )
        
        smart_money = (
            volume_zscore > self.VOLUME_ZSCORE_THRESHOLD or
            abs(cvd_divergence) > self.CVD_DIVERGENCE_THRESHOLD or
            absorption_ratio > self.ABSORPTION_THRESHOLD
        )
        
        return WhaleResult(
            whale_signal=signal,
            whale_score=score,
            volume_zscore=volume_zscore,
            cvd_divergence=cvd_divergence,
            absorption_ratio=absorption_ratio,
            aggressive_ratio=aggressive_ratio,
            oi_correlation=oi_correlation,
            smart_money_detected=smart_money
        )
    
    def _calculate_volume_zscore(self, candles: List[Dict]) -> float:
        """Volume z-score for anomaly detection."""
        volumes = np.array([c.get("volume", 0) for c in candles[-20:]])
        
        if len(volumes) < 2:
            return 0.0
        
        mean = np.mean(volumes[:-1])
        std = np.std(volumes[:-1])
        
        if std == 0:
            return 0.0
        
        return float((volumes[-1] - mean) / std)
    
    def _calculate_cvd_divergence(self, candles: List[Dict]) -> float:
        """CVD divergence from price."""
        if len(candles) < 10:
            return 0.0
        
        cvd = 0
        for c in candles[-10:]:
            if c["close"] > c["open"]:
                cvd += c.get("volume", 0)
            else:
                cvd -= c.get("volume", 0)
        
        # Compare with price direction
        price_change = (candles[-1]["close"] - candles[-10]["close"]) / candles[-10]["close"]
        
        # Normalize CVD
        total_volume = sum(c.get("volume", 0) for c in candles[-10:])
        cvd_normalized = cvd / total_volume if total_volume > 0 else 0
        
        # Divergence
        divergence = cvd_normalized * np.sign(price_change)
        
        return float(divergence)
    
    def _calculate_absorption(self, candles: List[Dict]) -> float:
        """Calculate absorption ratio (hidden orders)."""
        last = candles[-1]
        
        body = abs(last["close"] - last["open"])
        range_ = last["high"] - last["low"]
        
        if range_ == 0:
            return 0.0
        
        wick = range_ - body
        absorption = wick / range_
        
        # High absorption + close near middle = hidden orders
        midpoint = (last["high"] + last["low"]) / 2
        close_to_mid = 1 - abs(last["close"] - midpoint) / (range_ / 2)
        
        return float(absorption * close_to_mid)
    
    def _calculate_aggressive_ratio(self, candles: List[Dict]) -> float:
        """Calculate aggressive move ratio."""
        last = candles[-1]
        
        body = abs(last["close"] - last["open"])
        range_ = last["high"] - last["low"]
        
        if range_ == 0:
            return 0.0
        
        return float(body / range_)
    
    def _calculate_oi_correlation(self, candles: List[Dict], oi_data: List[float]) -> float:
        """Correlation between price and OI."""
        if len(oi_data) < 10 or len(candles) < 10:
            return 0.0
        
        prices = np.array([c["close"] for c in candles[-10:]])
        oi = np.array(oi_data[-10:])
        
        if len(prices) != len(oi):
            min_len = min(len(prices), len(oi))
            prices = prices[-min_len:]
            oi = oi[-min_len:]
        
        if len(prices) < 5:
            return 0.0
        
        # Pearson correlation
        p_mean = np.mean(prices)
        o_mean = np.mean(oi)
        
        numerator = np.sum((prices - p_mean) * (oi - o_mean))
        denominator = np.sqrt(np.sum((prices - p_mean)**2) * np.sum((oi - o_mean)**2))
        
        if denominator == 0:
            return 0.0
        
        return float(numerator / denominator)
    
    def _classify(self, volume_zscore: float, cvd_divergence: float,
                   absorption: float, aggressive: float, oi_corr: float) -> Tuple[WhaleSignal, float]:
        """Classify whale activity."""
        
        score = 0
        
        # Volume spike
        if volume_zscore > self.VOLUME_ZSCORE_THRESHOLD:
            score += 30
        
        # CVD divergence
        if abs(cvd_divergence) > self.CVD_DIVERGENCE_THRESHOLD:
            score += 25
        
        # Absorption
        if absorption > self.ABSORPTION_THRESHOLD:
            score += 20
        
        # Aggressive
        if aggressive > self.AGGRESSIVE_THRESHOLD:
            score += 25
        
        # OI correlation
        if abs(oi_corr) > 0.7:
            score += 15
        
        # Determine signal
        if score < 30:
            return WhaleSignal.NEUTRAL, score
        
        # Determine direction
        last = None
        # We need to check if this is accumulation or distribution
        if cvd_divergence > 0:
            if aggressive > 0.8:
                return WhaleSignal.AGGRESSIVE_BUY, score
            else:
                return WhaleSignal.HIDDEN_ACCUMULATION, score
        else:
            if aggressive > 0.8:
                return WhaleSignal.AGGRESSIVE_SELL, score
            else:
                return WhaleSignal.HIDDEN_DISTRIBUTION, score


# Global instance
_whale_detector = None

def get_detector() -> WhaleDetector:
    global _whale_detector
    if _whale_detector is None:
        _whale_detector = WhaleDetector()
    return _whale_detector


def detect_whale(candles: List[Dict], oi_data: List[float] = None) -> Dict:
    detector = get_detector()
    return detector.detect(candles, oi_data).to_dict()
