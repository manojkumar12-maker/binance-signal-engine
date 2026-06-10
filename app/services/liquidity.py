from typing import List, Dict, Optional


def detect_sweep(candles: List[Dict]) -> Optional[str]:
    if len(candles) < 20:
        return None
    
    recent = candles[-20:-1]
    last_candle = candles[-1]
    
    swing_highs = []
    swing_lows = []
    
    for i in range(1, len(recent) - 1):
        if recent[i]["high"] > recent[i-1]["high"] and recent[i]["high"] > recent[i+1]["high"]:
            swing_highs.append(recent[i]["high"])
        
        if recent[i]["low"] < recent[i-1]["low"] and recent[i]["low"] < recent[i+1]["low"]:
            swing_lows.append(recent[i]["low"])
    
    if not swing_highs or not swing_lows:
        return None
    
    recent_swing_high = max(swing_highs[-5:]) if len(swing_highs) >= 5 else max(swing_highs)
    recent_swing_low = min(swing_lows[-5:]) if len(swing_lows) >= 5 else min(swing_lows)
    
    last_high = last_candle["high"]
    last_low = last_candle["low"]
    last_close = last_candle["close"]
    
    if last_high > recent_swing_high:
        if last_close < recent_swing_high:
            return "SWEEP_HIGH_REJECTION"
        return "SWEEP_HIGH"
    
    if last_low < recent_swing_low:
        if last_close > recent_swing_low:
            return "SWEEP_LOW_REJECTION"
        return "SWEEP_LOW"
    
    return None


def align_sweep_with_trend(trend: str, sweep: Optional[str]) -> bool:
    if not sweep:
        return False
    
    if trend == "UPTREND" and sweep in ["SWEEP_LOW", "SWEEP_LOW_REJECTION"]:
        return True
    
    if trend == "DOWNTREND" and sweep in ["SWEEP_HIGH", "SWEEP_HIGH_REJECTION"]:
        return True
    
    return False
