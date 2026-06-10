"""
PHASE 6: SMART MONEY CONCEPTS (SMC) ENGINE
==========================================

PURPOSE:
Implement institutional Smart Money Concepts:
- Market Structure Break (BOS)
- Change of Character (CHoCH)
- Liquidity Sweeps
- Order Blocks
- Fair Value Gaps (FVG)

OUTPUT:
- SMC_SCORE (0-100)
- BIAS (BULLISH / BEARISH / NEUTRAL)
- ENTRY_ZONE
- STOP_LOSS
- TAKE_PROFIT

DETECTION:
1. BOS: Price breaks above/below previous swing point
2. CHoCH: Trend direction changes
3. Liquidity Sweep: Price takes out stops then reverses
4. Order Block: Last opposing candle before impulse
5. FVG: Imbalance zone with no overlap

THRESHOLDS:
- BOS + sweep = 80+ score
- CHoCH + FVG = 75+ score
- Order block + price return = 70+ score
"""

import numpy as np
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class SMCType(Enum):
    BOS = "BOS"
    CHoCH = "CHoCH"
    SWEEP = "SWEEP"
    ORDER_BLOCK = "ORDER_BLOCK"
    FVG = "FVG"
    NONE = "NONE"


@dataclass
class SMCResult:
    score: float
    bias: str
    smc_type: str
    entry_zone: float
    sl: float
    tp1: float
    tp2: float
    tp3: float
    bos_level: Optional[float]
    choch_level: Optional[float]
    sweep_level: Optional[float]
    ob_zone: Optional[Tuple[float, float]]
    fvg_zone: Optional[Tuple[float, float]]
    
    def to_dict(self) -> Dict:
        return {
            "score": round(self.score, 2),
            "bias": self.bias,
            "smc_type": self.smc_type,
            "entry_zone": round(self.entry_zone, 4),
            "sl": round(self.sl, 4),
            "tp1": round(self.tp1, 4),
            "tp2": round(self.tp2, 4),
            "tp3": round(self.tp3, 4),
            "bos_level": self.bos_level,
            "choch_level": self.choch_level,
            "sweep_level": self.sweep_level,
            "ob_zone": self.ob_zone,
            "fvg_zone": self.fvg_zone
        }


class SMCEngine:
    """
    Smart Money Concepts detection engine.
    """
    
    def __init__(self, lookback: int = 50):
        self.lookback = lookback
    
    def analyze(self, candles: List[Dict]) -> SMCResult:
        if len(candles) < 20:
            return SMCResult(
                score=0, bias="NEUTRAL", smc_type="NONE",
                entry_zone=0, sl=0, tp1=0, tp2=0, tp3=0,
                bos_level=None, choch_level=None, sweep_level=None,
                ob_zone=None, fvg_zone=None
            )
        
        # Detect patterns
        bos = self._detect_bos(candles)
        choch = self._detect_choch(candles)
        sweep = self._detect_sweep(candles)
        ob = self._detect_order_block(candles)
        fvg = self._detect_fvg(candles)
        
        # Determine bias
        bias = self._determine_bias(bos, choch, sweep, candles)
        
        # Calculate score
        score = self._calculate_score(bos, choch, sweep, ob, fvg)
        
        # Calculate levels
        entry, sl, tp1, tp2, tp3 = self._calculate_levels(
            candles, bias, sweep, ob, fvg
        )
        
        # Determine SMC type
        smc_type = self._determine_type(bos, choch, sweep, ob, fvg)
        
        return SMCResult(
            score=score,
            bias=bias,
            smc_type=smc_type,
            entry_zone=entry,
            sl=sl,
            tp1=tp1,
            tp2=tp2,
            tp3=tp3,
            bos_level=bos["level"] if bos else None,
            choch_level=choch["level"] if choch else None,
            sweep_level=sweep["level"] if sweep else None,
            ob_zone=ob["zone"] if ob else None,
            fvg_zone=fvg["zone"] if fvg else None
        )
    
    def _detect_bos(self, candles: List[Dict]) -> Optional[Dict]:
        """Detect Break of Structure."""
        if len(candles) < 10:
            return None
        
        # Find swing highs/lows
        highs = [c["high"] for c in candles[-10:]]
        lows = [c["low"] for c in candles[-10:]]
        
        # Find previous swing high
        swing_high = None
        for i in range(1, len(highs) - 1):
            if highs[i] > highs[i-1] and highs[i] > highs[i+1]:
                swing_high = highs[i]
        
        # Check if last candle broke above
        if swing_high and candles[-1]["close"] > swing_high:
            return {
                "type": "BOS_BULLISH",
                "level": swing_high,
                "strength": (candles[-1]["close"] - swing_high) / swing_high
            }
        
        # Find previous swing low
        swing_low = None
        for i in range(1, len(lows) - 1):
            if lows[i] < lows[i-1] and lows[i] < lows[i+1]:
                swing_low = lows[i]
        
        # Check if last candle broke below
        if swing_low and candles[-1]["close"] < swing_low:
            return {
                "type": "BOS_BEARISH",
                "level": swing_low,
                "strength": (swing_low - candles[-1]["close"]) / swing_low
            }
        
        return None
    
    def _detect_choch(self, candles: List[Dict]) -> Optional[Dict]:
        """Detect Change of Character."""
        if len(candles) < 20:
            return None
        
        # Check for trend change
        prev_trend = self._get_trend(candles[-20:-10])
        current_trend = self._get_trend(candles[-10:])
        
        if prev_trend == "BEARISH" and current_trend == "BULLISH":
            return {
                "type": "CHoCH_BULLISH",
                "level": candles[-10]["low"],
                "strength": 1.0
            }
        
        if prev_trend == "BULLISH" and current_trend == "BEARISH":
            return {
                "type": "CHoCH_BEARISH",
                "level": candles[-10]["high"],
                "strength": 1.0
            }
        
        return None
    
    def _detect_sweep(self, candles: List[Dict]) -> Optional[Dict]:
        """Detect liquidity sweep."""
        if len(candles) < 5:
            return None
        
        # Check for sweep of previous high/low
        prev_high = max(c["high"] for c in candles[-5:-1])
        prev_low = min(c["low"] for c in candles[-5:-1])
        
        last = candles[-1]
        
        # Sweep high and reverse
        if last["high"] > prev_high and last["close"] < last["high"]:
            return {
                "type": "SWEEP_HIGH",
                "level": prev_high,
                "rejection": (last["high"] - last["close"]) / last["high"]
            }
        
        # Sweep low and reverse
        if last["low"] < prev_low and last["close"] > last["low"]:
            return {
                "type": "SWEEP_LOW",
                "level": prev_low,
                "rejection": (last["close"] - last["low"]) / last["low"]
            }
        
        return None
    
    def _detect_order_block(self, candles: List[Dict]) -> Optional[Dict]:
        """Detect Order Block."""
        if len(candles) < 10:
            return None
        
        # Look for last opposing candle before strong move
        for i in range(len(candles) - 5, len(candles) - 1):
            c = candles[i]
            next_c = candles[i + 1]
            
            # Bullish OB: bearish candle followed by strong bullish move
            if c["close"] < c["open"]:
                if next_c["close"] > next_c["open"] and next_c["close"] > c["high"]:
                    return {
                        "type": "BULLISH_OB",
                        "zone": (c["low"], c["high"]),
                        "strength": (next_c["close"] - c["high"]) / c["high"]
                    }
            
            # Bearish OB: bullish candle followed by strong bearish move
            if c["close"] > c["open"]:
                if next_c["close"] < next_c["open"] and next_c["close"] < c["low"]:
                    return {
                        "type": "BEARISH_OB",
                        "zone": (c["low"], c["high"]),
                        "strength": (c["low"] - next_c["close"]) / c["low"]
                    }
        
        return None
    
    def _detect_fvg(self, candles: List[Dict]) -> Optional[Dict]:
        """Detect Fair Value Gap."""
        if len(candles) < 5:
            return None
        
        # Look for 3-candle pattern with gap
        for i in range(len(candles) - 4, len(candles) - 2):
            c1 = candles[i]
            c2 = candles[i + 1]
            c3 = candles[i + 2]
            
            # Bullish FVG
            if c1["close"] < c1["open"] and c3["close"] > c3["open"]:
                if c3["low"] > c1["high"]:
                    return {
                        "type": "BULLISH_FVG",
                        "zone": (c1["high"], c3["low"]),
                        "strength": (c3["low"] - c1["high"]) / c1["high"]
                    }
            
            # Bearish FVG
            if c1["close"] > c1["open"] and c3["close"] < c3["open"]:
                if c3["high"] < c1["low"]:
                    return {
                        "type": "BEARISH_FVG",
                        "zone": (c3["high"], c1["low"]),
                        "strength": (c1["low"] - c3["high"]) / c1["low"]
                    }
        
        return None
    
    def _get_trend(self, candles: List[Dict]) -> str:
        """Get simple trend direction."""
        if len(candles) < 5:
            return "NEUTRAL"
        
        highs = [c["high"] for c in candles]
        lows = [c["low"] for c in candles]
        
        if highs[-1] > highs[0] and lows[-1] > lows[0]:
            return "BULLISH"
        
        if highs[-1] < highs[0] and lows[-1] < lows[0]:
            return "BEARISH"
        
        return "NEUTRAL"
    
    def _determine_bias(self, bos: Optional[Dict], choch: Optional[Dict],
                        sweep: Optional[Dict], candles: List[Dict]) -> str:
        """Determine directional bias."""
        bullish_signals = 0
        bearish_signals = 0
        
        if bos:
            if "BULLISH" in bos["type"]:
                bullish_signals += 1
            else:
                bearish_signals += 1
        
        if choch:
            if "BULLISH" in choch["type"]:
                bullish_signals += 1
            else:
                bearish_signals += 1
        
        if sweep:
            if "SWEEP_LOW" in sweep["type"]:
                bullish_signals += 1
            else:
                bearish_signals += 1
        
        if bullish_signals > bearish_signals:
            return "BULLISH"
        elif bearish_signals > bullish_signals:
            return "BEARISH"
        
        return "NEUTRAL"
    
    def _calculate_score(self, bos: Optional[Dict], choch: Optional[Dict],
                         sweep: Optional[Dict], ob: Optional[Dict],
                         fvg: Optional[Dict]) -> float:
        """Calculate SMC score."""
        score = 0
        
        if bos:
            score += 30
        
        if choch:
            score += 25
        
        if sweep:
            score += 20
        
        if ob:
            score += 15
        
        if fvg:
            score += 10
        
        # Combo bonus
        if bos and sweep:
            score += 15
        
        if choch and fvg:
            score += 10
        
        return min(100, score)
    
    def _calculate_levels(self, candles: List[Dict], bias: str,
                          sweep: Optional[Dict], ob: Optional[Dict],
                          fvg: Optional[Dict]) -> Tuple[float, float, float, float, float]:
        """Calculate entry, SL, TP levels."""
        current = candles[-1]["close"]
        
        if bias == "BULLISH":
            entry = current
            
            if fvg:
                entry = fvg["zone"][0]
            elif ob:
                entry = ob["zone"][1]
            
            sl = entry * 0.98
            tp1 = entry * 1.02
            tp2 = entry * 1.04
            tp3 = entry * 1.06
        
        elif bias == "BEARISH":
            entry = current
            
            if fvg:
                entry = fvg["zone"][1]
            elif ob:
                entry = ob["zone"][0]
            
            sl = entry * 1.02
            tp1 = entry * 0.98
            tp2 = entry * 0.96
            tp3 = entry * 0.94
        
        else:
            entry = current
            sl = entry * 0.98
            tp1 = entry * 1.02
            tp2 = entry * 1.04
            tp3 = entry * 1.06
        
        return entry, sl, tp1, tp2, tp3
    
    def _determine_type(self, bos: Optional[Dict], choch: Optional[Dict],
                        sweep: Optional[Dict], ob: Optional[Dict],
                        fvg: Optional[Dict]) -> str:
        """Determine SMC type string."""
        types = []
        
        if bos:
            types.append(bos["type"])
        if choch:
            types.append(choch["type"])
        if sweep:
            types.append(sweep["type"])
        if ob:
            types.append(ob["type"])
        if fvg:
            types.append(fvg["type"])
        
        return " | ".join(types) if types else "NONE"


# Global instance
_smc_engine = None

def get_engine() -> SMCEngine:
    global _smc_engine
    if _smc_engine is None:
        _smc_engine = SMCEngine()
    return _smc_engine


def analyze_smc(candles: List[Dict]) -> Dict:
    engine = get_engine()
    return engine.analyze(candles).to_dict()
