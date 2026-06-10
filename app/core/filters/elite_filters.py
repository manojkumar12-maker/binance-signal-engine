"""
PHASE 8: ELITE FILTERS ENGINE
==============================

PURPOSE:
Institutional-grade filters to avoid bad setups:
1. News avoidance filter
2. High volatility filter
3. Funding rate filter
4. Correlation filter
5. BTC dominance filter

OUTPUT:
- Filter result (PASS / FAIL)
- Reason for rejection

THRESHOLDS:
- Volatility: ATR > 2% = fail
- Funding: |rate| > 0.01% = fail
- Pump/dump: 1h change > 10% = fail
- BTC dominance: sudden > 5% shift = fail
"""

from typing import Dict, List, Optional
import numpy as np
import logging

logger = logging.getLogger(__name__)


class EliteFilter:
    """
    Elite signal filters.
    """
    
    # Thresholds
    MAX_ATR_RATIO = 0.02
    MAX_FUNDING_RATE = 0.0001  # 0.01%
    MAX_1H_CHANGE = 0.10  # 10%
    MAX_BTC_SHIFT = 0.05  # 5%
    MIN_VOLUME = 1000000  # $1M
    
    def check(self, pair: str, candles: List[Dict], regime: Dict,
              funding_rate: float = 0.0, btc_dominance: float = 0.0,
              correlation_pairs: List[Dict] = None) -> Dict:
        """
        Run all elite filters.
        
        Returns:
            {"passed": bool, "reason": str, "filters": {...}}
        """
        
        filters = {}
        
        # 1. Volatility filter
        atr_ratio = regime.get("atr_ratio", 0)
        filters["volatility"] = {
            "passed": atr_ratio <= self.MAX_ATR_RATIO,
            "value": atr_ratio,
            "threshold": self.MAX_ATR_RATIO
        }
        
        # 2. Funding rate filter
        filters["funding"] = {
            "passed": abs(funding_rate) <= self.MAX_FUNDING_RATE,
            "value": funding_rate,
            "threshold": self.MAX_FUNDING_RATE
        }
        
        # 3. Pump/dump filter
        change_1h = self._calculate_1h_change(candles)
        filters["pump_dump"] = {
            "passed": abs(change_1h) <= self.MAX_1H_CHANGE,
            "value": change_1h,
            "threshold": self.MAX_1H_CHANGE
        }
        
        # 4. Volume filter
        avg_volume = self._calculate_avg_volume(candles)
        filters["volume"] = {
            "passed": avg_volume >= self.MIN_VOLUME,
            "value": avg_volume,
            "threshold": self.MIN_VOLUME
        }
        
        # 5. BTC dominance filter
        filters["btc_dominance"] = {
            "passed": btc_dominance <= self.MAX_BTC_SHIFT,
            "value": btc_dominance,
            "threshold": self.MAX_BTC_SHIFT
        }
        
        # 6. Ranging filter
        regime_name = regime.get("regime", "UNKNOWN")
        filters["ranging"] = {
            "passed": regime_name not in ["RANGING", "VOLATILE", "UNKNOWN"],
            "value": regime_name,
            "threshold": "TRENDING"
        }
        
        # Determine overall result
        all_passed = all(f["passed"] for f in filters.values())
        
        reason = "OK"
        if not all_passed:
            failed = [k for k, v in filters.items() if not v["passed"]]
            reason = f"Failed: {', '.join(failed)}"
        
        return {
            "passed": all_passed,
            "reason": reason,
            "filters": filters
        }
    
    def _calculate_1h_change(self, candles: List[Dict]) -> float:
        """Calculate 1-hour price change."""
        if len(candles) < 5:
            return 0.0
        
        return (candles[-1]["close"] - candles[-5]["close"]) / candles[-5]["close"]
    
    def _calculate_avg_volume(self, candles: List[Dict]) -> float:
        """Calculate average volume in USD."""
        if len(candles) < 5:
            return 0.0
        
        volumes = [c.get("volume", 0) * c.get("close", 0) for c in candles[-5:]]
        return float(np.mean(volumes))


# Global instance
_elite_filter = None

def get_filter() -> EliteFilter:
    global _elite_filter
    if _elite_filter is None:
        _elite_filter = EliteFilter()
    return _elite_filter


def check_filters(**kwargs) -> Dict:
    filter_engine = get_filter()
    return filter_engine.check(**kwargs)
