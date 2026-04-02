from typing import List, Dict


def detect_trend(candles: List[Dict]) -> str:
    if len(candles) < 5:
        return "RANGE"
    
    recent = candles[-5:]
    
    highs = [c["high"] for c in recent]
    lows = [c["low"] for c in recent]
    
    current_high = highs[-1]
    current_low = lows[-1]
    prev_high = highs[-2]
    prev_low = lows[-2]
    second_prev_high = highs[-3]
    second_prev_low = lows[-3]
    
    if current_high > prev_high and current_high > second_prev_high:
        if current_low > prev_low and current_low > second_prev_low:
            return "UPTREND"
    
    if current_high < prev_high and current_high < second_prev_high:
        if current_low < prev_low and current_low < second_prev_low:
            return "DOWNTREND"
    
    return "RANGE"


def detect_trend_strength(candles: List[Dict]) -> float:
    if len(candles) < 10:
        return 0.0
    
    recent = candles[-10:]
    
    high_count = 0
    for i in range(1, len(recent) - 1):
        if recent[i]["high"] > recent[i-1]["high"] and recent[i]["high"] > recent[i+1]["high"]:
            high_count += 1
    
    low_count = 0
    for i in range(1, len(recent) - 1):
        if recent[i]["low"] < recent[i-1]["low"] and recent[i]["low"] < recent[i+1]["low"]:
            low_count += 1
    
    trend_strength = (high_count + low_count) / (len(recent) - 2)
    return min(trend_strength, 1.0)


def candle_strength(candle: Dict) -> int:
    body = abs(candle['close'] - candle['open'])
    range_ = candle['high'] - candle['low']
    
    if range_ == 0:
        return 0
    
    return int((body / range_) * 20)


def detect_htf_trend(candles_4h: List[Dict]) -> str:
    return detect_trend(candles_4h)
