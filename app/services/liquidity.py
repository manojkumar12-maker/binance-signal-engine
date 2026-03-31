from typing import List, Dict, Optional


def detect_sweep(candles: List[Dict]) -> Optional[str]:
    if len(candles) < 20:
        return None
    
    recent = candles[-20:-1]
    
    swing_highs = []
    swing_lows = []
    
    for i in range(1, len(recent) - 1):
        if recent[i]["high"] > recent[i-1]["high"] and recent[i]["high"] > recent[i+1]["high"]:
            swing_highs.append(recent[i]["high"])
        
        if recent[i]["low"] < recent[i-1]["low"] and recent[i]["low"] < recent[i+1]["low"]:
            swing_lows.append(recent[i]["low"])
    
    if not swing_highs or not swing_lows:
        return None
    
    last_high = candles[-1]["high"]
    last_low = candles[-1]["low"]
    
    equal_highs = [h for h in swing_highs if abs(h - last_high) < last_high * 0.001]
    equal_lows = [l for l in swing_lows if abs(l - last_low) < last_low * 0.001]
    
    recent_swing_high = max(swing_highs[-5:]) if len(swing_highs) >= 5 else max(swing_highs)
    recent_swing_low = min(swing_lows[-5:]) if len(swing_lows) >= 5 else min(swing_lows)
    
    if last_high > recent_swing_high:
        return "SWEEP_HIGH"
    
    if last_low < recent_swing_low:
        return "SWEEP_LOW"
    
    return None
