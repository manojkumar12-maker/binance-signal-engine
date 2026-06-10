"""
PHASE 7: MULTI-LAYER CONFIDENCE ENGINE
=======================================

PURPOSE:
Institutional-grade confidence scoring combining all indicators.

WEIGHTS:
- Trend Alignment = 20
- RSI = 5
- MACD = 5
- Volume = 10
- OI = 15
- Liquidation = 15
- Whale Activity = 15
- SMC = 10
- Market Regime = 5

SCORING:
- Each component scored 0-100
- Weighted sum normalized to 0-100
- Only signals >= 75 pass
- Sniper signals >= 90

OPTIMIZATION:
- Adaptive weights based on market regime
- Penalty for conflicting signals
- Bonus for confluence
"""

from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class ConfidenceEngine:
    """
    Multi-layer confidence scoring engine.
    """
    
    # Default weights
    WEIGHTS = {
        "trend": 20,
        "rsi": 5,
        "macd": 5,
        "volume": 10,
        "oi": 15,
        "liquidation": 15,
        "whale": 15,
        "smc": 10,
        "regime": 5
    }
    
    # Adaptive weights by regime
    REGIME_WEIGHTS = {
        "TRENDING_BULL": {"trend": 25, "oi": 20, "whale": 10},
        "TRENDING_BEAR": {"trend": 25, "oi": 20, "whale": 10},
        "RANGING": {"smc": 15, "rsi": 10, "volume": 15},
        "VOLATILE": {"liquidation": 25, "whale": 20},
        "ACCUMULATION": {"whale": 25, "volume": 15},
        "DISTRIBUTION": {"whale": 25, "volume": 15}
    }
    
    def calculate(self, trend: float = 50, rsi: float = 50, macd: float = 50,
                  volume_profile: Dict = None, oi: Dict = None,
                  liquidation: Dict = None, whale: Dict = None,
                  smc: Dict = None, regime: Dict = None) -> Dict:
        """
        Calculate multi-layer confidence score.
        
        Args:
            trend: Trend strength score (0-100)
            rsi: RSI score (0-100)
            macd: MACD score (0-100)
            volume_profile: Volume profile result dict
            oi: OI analysis result dict
            liquidation: Liquidation tracker result dict
            whale: Whale detector result dict
            smc: SMC engine result dict
            regime: Regime detector result dict
            
        Returns:
            Dict with total score and breakdown
        """
        
        # Get adaptive weights
        weights = self._get_weights(regime)
        
        # Extract scores from dicts
        volume_score = volume_profile.get("volume_score", 50) if volume_profile else 50
        oi_score = oi.get("oi_score", 50) if oi else 50
        liq_score = liquidation.get("score", 50) if liquidation else 50
        whale_score = whale.get("whale_score", 50) if whale else 50
        smc_score = smc.get("score", 50) if smc else 50
        regime_score = 100 if regime and regime.get("tradeable", False) else 0
        
        # Normalize individual scores
        scores = {
            "trend": max(0, min(100, trend)),
            "rsi": max(0, min(100, rsi)),
            "macd": max(0, min(100, macd)),
            "volume": max(0, min(100, volume_score)),
            "oi": max(0, min(100, oi_score)),
            "liquidation": max(0, min(100, liq_score)),
            "whale": max(0, min(100, whale_score)),
            "smc": max(0, min(100, smc_score)),
            "regime": max(0, min(100, regime_score))
        }
        
        # Calculate weighted sum
        total = 0
        max_total = 0
        for key, weight in weights.items():
            total += scores[key] * weight
            max_total += 100 * weight
        
        final_score = (total / max_total) * 100 if max_total > 0 else 0
        
        # Apply penalties and bonuses
        final_score = self._apply_confluence(final_score, scores)
        final_score = self._apply_penalties(final_score, scores, regime)
        
        # Determine tier
        tier = self._get_tier(final_score)
        
        return {
            "total": round(final_score, 1),
            "tier": tier,
            "breakdown": {k: round(v, 1) for k, v in scores.items()},
            "weights": weights,
            "passed": final_score >= 75,
            "sniper": final_score >= 90
        }
    
    def _get_weights(self, regime: Optional[Dict]) -> Dict:
        """Get adaptive weights based on regime."""
        weights = self.WEIGHTS.copy()
        
        if regime and "regime" in regime:
            regime_name = regime["regime"]
            if regime_name in self.REGIME_WEIGHTS:
                weights.update(self.REGIME_WEIGHTS[regime_name])
        
        return weights
    
    def _apply_confluence(self, score: float, scores: Dict) -> float:
        """Bonus for confluence of signals."""
        strong_signals = sum(1 for s in scores.values() if s >= 70)
        
        if strong_signals >= 5:
            score += 10
        elif strong_signals >= 3:
            score += 5
        
        return min(100, score)
    
    def _apply_penalties(self, score: float, scores: Dict, regime: Optional[Dict]) -> float:
        """Penalties for conflicting signals."""
        # Low trend score penalty
        if scores["trend"] < 30:
            score -= 10
        
        # Low regime score penalty
        if scores["regime"] < 50:
            score -= 15
        
        # Conflicting whale and OI
        if scores["whale"] > 70 and scores["oi"] < 30:
            score -= 10
        
        # Conflicting SMC and trend
        if scores["smc"] > 70 and scores["trend"] < 30:
            score -= 10
        
        return max(0, score)
    
    def _get_tier(self, score: float) -> str:
        """Get signal tier."""
        if score >= 90:
            return "SNIPER"
        elif score >= 80:
            return "ELITE"
        elif score >= 75:
            return "STANDARD"
        elif score >= 60:
            return "WATCH"
        else:
            return "REJECT"


# Global instance
_confidence_engine = None

def get_engine() -> ConfidenceEngine:
    global _confidence_engine
    if _confidence_engine is None:
        _confidence_engine = ConfidenceEngine()
    return _confidence_engine


def calculate_confidence(**kwargs) -> Dict:
    engine = get_engine()
    return engine.calculate(**kwargs)
