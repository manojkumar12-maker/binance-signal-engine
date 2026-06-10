"""
PHASE 9: SNIPER MODE ENGINE
============================

PURPOSE:
Generate only the highest-probability signals.

REQUIREMENTS:
- Maximum 1-3 trades/day
- Only confidence >= 90
- Only strongest market structure
- Only strongest whale signals
- Only strongest OI confirmation

OUTPUT:
- SNIPER_LONG / SNIPER_SHORT
- Sniper score (0-100)

LOGIC:
1. Confidence >= 90
2. SMC score >= 80
3. Whale score >= 75
4. OI score >= 70
5. Regime must be TRENDING_BULL/BEAR
6. No conflicting signals
7. Max 1 signal per 4 hours per pair
"""

from typing import Dict, List
import time
import logging

logger = logging.getLogger(__name__)


class SniperMode:
    """
    Elite sniper signal generator.
    """
    
    MIN_CONFIDENCE = 90
    MIN_SMC_SCORE = 80
    MIN_WHALE_SCORE = 75
    MIN_OI_SCORE = 70
    COOLDOWN_SECONDS = 14400  # 4 hours
    MAX_DAILY_SIGNALS = 3
    
    def __init__(self):
        self.last_signals = {}  # pair -> timestamp
        self.daily_count = 0
        self.daily_reset = time.time()
    
    def evaluate(self, confidence: Dict, smc: Dict, whale: Dict,
                 oi: Dict, regime: Dict) -> Dict:
        """
        Evaluate if signal qualifies for sniper mode.
        """
        
        # Reset daily count
        if time.time() - self.daily_reset > 86400:
            self.daily_count = 0
            self.daily_reset = time.time()
        
        # Check daily limit
        if self.daily_count >= self.MAX_DAILY_SIGNALS:
            return {
                "sniper_signal": "NONE",
                "reason": "Daily limit reached",
                "passed": False
            }
        
        # Extract scores
        conf_score = confidence.get("total", 0)
        smc_score = smc.get("score", 0)
        whale_score = whale.get("whale_score", 0)
        oi_score = oi.get("oi_score", 50)
        regime_name = regime.get("regime", "UNKNOWN")
        
        # Check all thresholds
        checks = {
            "confidence": conf_score >= self.MIN_CONFIDENCE,
            "smc": smc_score >= self.MIN_SMC_SCORE,
            "whale": whale_score >= self.MIN_WHALE_SCORE,
            "oi": oi_score >= self.MIN_OI_SCORE,
            "regime": regime_name in ["TRENDING_BULL", "TRENDING_BEAR"]
        }
        
        # Check conflicts
        bias = smc.get("bias", "NEUTRAL")
        whale_signal = whale.get("whale_signal", "NEUTRAL")
        
        conflicts = False
        if whale_signal == "AGGRESSIVE_SELL" and bias == "BULLISH":
            conflicts = True
        if whale_signal == "AGGRESSIVE_BUY" and bias == "BEARISH":
            conflicts = True
        
        # Check if all passed
        all_passed = all(checks.values()) and not conflicts
        
        if not all_passed:
            failed = [k for k, v in checks.items() if not v]
            if conflicts:
                failed.append("conflict")
            return {
                "sniper_signal": "NONE",
                "reason": f"Failed: {', '.join(failed)}",
                "passed": False,
                "checks": checks
            }
        
        # Generate signal
        signal = "SNIPER_LONG" if bias == "BULLISH" else "SNIPER_SHORT"
        
        self.daily_count += 1
        
        return {
            "sniper_signal": signal,
            "passed": True,
            "reason": "All checks passed",
            "checks": checks,
            "scores": {
                "confidence": conf_score,
                "smc": smc_score,
                "whale": whale_score,
                "oi": oi_score
            }
        }
    
    def can_signal(self, pair: str) -> bool:
        """Check if pair is in cooldown."""
        if pair in self.last_signals:
            if time.time() - self.last_signals[pair] < self.COOLDOWN_SECONDS:
                return False
        return True
    
    def record_signal(self, pair: str):
        """Record signal timestamp."""
        self.last_signals[pair] = time.time()


# Global instance
_sniper_mode = None

def get_sniper() -> SniperMode:
    global _sniper_mode
    if _sniper_mode is None:
        _sniper_mode = SniperMode()
    return _sniper_mode


def evaluate_sniper(**kwargs) -> Dict:
    sniper = get_sniper()
    return sniper.evaluate(**kwargs)
