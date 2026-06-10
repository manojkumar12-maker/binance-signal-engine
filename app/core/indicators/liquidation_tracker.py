"""
PHASE 3: LIQUIDATION INTELLIGENCE ENGINE
=======================================

PURPOSE:
Detect liquidation cascades, clusters, and squeeze opportunities.

DETECTION:
1. Liquidation Clusters: Large wicks + volume spikes
2. Long Squeeze: Rapid drop + high volume + wick rejection
3. Short Squeeze: Rapid spike + high volume + wick rejection
4. Liquidation Cascade: Multiple consecutive large wicks

SCORING:
- LIQUIDATION_SCORE (0-100)
- Higher = stronger liquidation event (tradeable reversal)

FORMULAS:
Wick_Ratio = wick_size / avg_wick
Liquidation_Strength = wick_ratio * volume_ratio * speed_ratio

THRESHOLDS:
- Wick ratio > 3.0 = liquidation wick
- Volume ratio > 3.0 = liquidation volume
- Speed > 2% in 1 candle = cascade speed
"""

import numpy as np
from typing import List, Dict, Tuple
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class LiquidationType(Enum):
    LONG_SQUEEZE = "LONG_SQUEEZE"
    SHORT_SQUEEZE = "SHORT_SQUEEZE"
    LONG_LIQUIDATION = "LONG_LIQUIDATION"
    SHORT_LIQUIDATION = "SHORT_LIQUIDATION"
    CASCADE = "CASCADE"
    CLUSTER = "CLUSTER"
    NONE = "NONE"


@dataclass
class LiquidationResult:
    liquidation_type: LiquidationType
    score: float
    wick_ratio: float
    volume_ratio: float
    speed_ratio: float
    cascade_count: int
    direction: str
    tradeable: bool
    
    def to_dict(self) -> Dict:
        return {
            "liquidation_type": self.liquidation_type.value,
            "score": round(self.score, 2),
            "wick_ratio": round(self.wick_ratio, 2),
            "volume_ratio": round(self.volume_ratio, 2),
            "speed_ratio": round(self.speed_ratio, 2),
            "cascade_count": self.cascade_count,
            "direction": self.direction,
            "tradeable": self.tradeable
        }


class LiquidationTracker:
    """
    Detect liquidation events from candle patterns.
    """
    
    WICK_THRESHOLD = 3.0
    VOLUME_THRESHOLD = 3.0
    SPEED_THRESHOLD = 0.02
    CASCADE_COUNT = 3
    
    def detect(self, candles: List[Dict]) -> LiquidationResult:
        if len(candles) < 20:
            return LiquidationResult(
                liquidation_type=LiquidationType.NONE,
                score=0, wick_ratio=0, volume_ratio=0,
                speed_ratio=0, cascade_count=0,
                direction="NEUTRAL", tradeable=False
            )
        
        # Calculate metrics
        wick_ratio = self._calculate_wick_ratio(candles)
        volume_ratio = self._calculate_volume_ratio(candles)
        speed_ratio = self._calculate_speed_ratio(candles)
        cascade_count = self._detect_cascade(candles)
        
        # Determine direction
        direction = self._determine_direction(candles)
        
        # Classify
        liq_type, score = self._classify(
            wick_ratio, volume_ratio, speed_ratio, cascade_count, direction
        )
        
        tradeable = score > 70 and liq_type in [
            LiquidationType.LONG_SQUEEZE,
            LiquidationType.SHORT_SQUEEZE,
            LiquidationType.CASCADE
        ]
        
        return LiquidationResult(
            liquidation_type=liq_type,
            score=score,
            wick_ratio=wick_ratio,
            volume_ratio=volume_ratio,
            speed_ratio=speed_ratio,
            cascade_count=cascade_count,
            direction=direction,
            tradeable=tradeable
        )
    
    def _calculate_wick_ratio(self, candles: List[Dict]) -> float:
        """Ratio of current wick to average wick."""
        recent = candles[-10:]
        
        wicks = []
        for c in recent[:-1]:
            body = abs(c["close"] - c["open"])
            range_ = c["high"] - c["low"]
            wick = range_ - body
            wicks.append(wick)
        
        avg_wick = np.mean(wicks) if wicks else 0
        
        last = candles[-1]
        last_body = abs(last["close"] - last["open"])
        last_range = last["high"] - last["low"]
        last_wick = last_range - last_body
        
        if avg_wick == 0:
            return 0
        
        return float(last_wick / avg_wick)
    
    def _calculate_volume_ratio(self, candles: List[Dict]) -> float:
        """Ratio of current volume to average volume."""
        volumes = [c.get("volume", 0) for c in candles[-20:]]
        
        if len(volumes) < 2:
            return 0
        
        avg_vol = np.mean(volumes[:-1])
        last_vol = volumes[-1]
        
        if avg_vol == 0:
            return 0
        
        return float(last_vol / avg_vol)
    
    def _calculate_speed_ratio(self, candles: List[Dict]) -> float:
        """Price change speed as ratio."""
        if len(candles) < 2:
            return 0
        
        change = abs(candles[-1]["close"] - candles[-2]["close"]) / candles[-2]["close"]
        return float(change)
    
    def _detect_cascade(self, candles: List[Dict]) -> int:
        """Count consecutive liquidation candles."""
        if len(candles) < 5:
            return 0
        
        cascade = 0
        for c in candles[-5:]:
            body = abs(c["close"] - c["open"])
            range_ = c["high"] - c["low"]
            wick = range_ - body
            
            avg_range = range_ if range_ > 0 else 1
            wick_ratio = wick / avg_range
            
            if wick_ratio > 0.6:  # Large wick
                cascade += 1
        
        return cascade
    
    def _determine_direction(self, candles: List[Dict]) -> str:
        """Determine liquidation direction."""
        if len(candles) < 2:
            return "NEUTRAL"
        
        last = candles[-1]
        prev = candles[-2]
        
        # Large wick down = long liquidation
        if last["low"] < prev["low"] and last["close"] > last["low"]:
            return "BULLISH"  # Longs liquidated, bounce likely
        
        # Large wick up = short liquidation
        if last["high"] > prev["high"] and last["close"] < last["high"]:
            return "BEARISH"  # Shorts liquidated, drop likely
        
        return "NEUTRAL"
    
    def _classify(self, wick_ratio: float, volume_ratio: float,
                   speed_ratio: float, cascade_count: int, direction: str) -> Tuple[LiquidationType, float]:
        """Classify liquidation type and score."""
        
        strength = wick_ratio * volume_ratio * (1 + speed_ratio * 10)
        
        if cascade_count >= self.CASCADE_COUNT:
            return LiquidationType.CASCADE, min(100, strength * 15)
        
        if wick_ratio > self.WICK_THRESHOLD and volume_ratio > self.VOLUME_THRESHOLD:
            if direction == "BULLISH":
                return LiquidationType.LONG_SQUEEZE, min(100, strength * 12)
            else:
                return LiquidationType.SHORT_SQUEEZE, min(100, strength * 12)
        
        if wick_ratio > self.WICK_THRESHOLD:
            if direction == "BULLISH":
                return LiquidationType.LONG_LIQUIDATION, min(100, wick_ratio * 10)
            else:
                return LiquidationType.SHORT_LIQUIDATION, min(100, wick_ratio * 10)
        
        if volume_ratio > self.VOLUME_THRESHOLD and speed_ratio > self.SPEED_THRESHOLD:
            return LiquidationType.CLUSTER, min(100, volume_ratio * speed_ratio * 100)
        
        return LiquidationType.NONE, 0
    
    def get_trade_signal(self, result: LiquidationResult) -> Dict:
        """Convert liquidation event to trade signal."""
        if not result.tradeable:
            return {"signal": "NONE", "reason": "Not tradeable"}
        
        if result.liquidation_type in [LiquidationType.LONG_SQUEEZE, LiquidationType.LONG_LIQUIDATION]:
            return {
                "signal": "BUY",
                "reason": f"{result.liquidation_type.value} - reversal opportunity",
                "score": result.score
            }
        
        if result.liquidation_type in [LiquidationType.SHORT_SQUEEZE, LiquidationType.SHORT_LIQUIDATION]:
            return {
                "signal": "SELL",
                "reason": f"{result.liquidation_type.value} - reversal opportunity",
                "score": result.score
            }
        
        return {"signal": "NONE", "reason": "No clear direction"}


# Global instance
_liquidation_tracker = None

def get_tracker() -> LiquidationTracker:
    global _liquidation_tracker
    if _liquidation_tracker is None:
        _liquidation_tracker = LiquidationTracker()
    return _liquidation_tracker


def detect_liquidation(candles: List[Dict]) -> Dict:
    tracker = get_tracker()
    return tracker.detect(candles).to_dict()
