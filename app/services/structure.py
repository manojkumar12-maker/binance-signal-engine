from typing import List, Dict, Optional, Tuple


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


def detect_swing_levels(candles: List[Dict], lookback: int = 20) -> Tuple[List[float], List[float]]:
    if len(candles) < 3:
        return [], []
    
    recent = candles[-lookback:] if len(candles) > lookback else candles
    
    swing_highs = []
    swing_lows = []
    
    for i in range(1, len(recent) - 1):
        if recent[i]["high"] > recent[i-1]["high"] and recent[i]["high"] > recent[i+1]["high"]:
            swing_highs.append(recent[i]["high"])
        if recent[i]["low"] < recent[i-1]["low"] and recent[i]["low"] < recent[i+1]["low"]:
            swing_lows.append(recent[i]["low"])
    
    return swing_highs, swing_lows


def detect_bos(candles: List[Dict], trend: str, lookback: int = 5) -> Optional[str]:
    if len(candles) < lookback + 2:
        return None
    
    recent = candles[-lookback-1:]
    
    swing_highs, swing_lows = detect_swing_levels(recent, lookback)
    
    if not swing_highs or not swing_lows:
        return None
    
    last_high = recent[-1]["high"]
    last_low = recent[-1]["low"]
    prev_high = recent[-2]["high"]
    prev_low = recent[-2]["low"]
    
    if trend == "UPTREND":
        max_swing_high = max(swing_highs[:-1]) if len(swing_highs) > 1 else max(swing_highs)
        if last_high > max_swing_high:
            return "BOS_UP"
    
    elif trend == "DOWNTREND":
        min_swing_low = min(swing_lows[:-1]) if len(swing_lows) > 1 else min(swing_lows)
        if last_low < min_swing_low:
            return "BOS_DOWN"
    
    return None


def detect_choch(candles: List[Dict], prev_trend: str, lookback: int = 10) -> Optional[str]:
    if len(candles) < lookback + 5:
        return None
    
    recent = candles[-lookback:]
    prev_recent = candles[-lookback-5:-lookback]
    
    prev_trend_detected = detect_trend(prev_recent) if len(prev_recent) >= 5 else "RANGE"
    current_trend = detect_trend(recent)
    
    if prev_trend_detected == "DOWNTREND" and current_trend == "UPTREND":
        return "CHoCH_UP"
    elif prev_trend_detected == "UPTREND" and current_trend == "DOWNTREND":
        return "CHoCH_DOWN"
    
    return None


def detect_fvg(candles: List[Dict], lookback: int = 3) -> Optional[Dict]:
    if len(candles) < lookback:
        return None
    
    recent = candles[-lookback:]
    
    for i in range(len(recent) - 2):
        c1 = recent[i]
        c2 = recent[i + 1]
        c3 = recent[i + 2]
        
        c1_low = c1.get('low', c1.get('open', 0))
        c1_high = c1.get('high', c1.get('close', 0))
        c2_low = c2.get('low', c2.get('open', 0))
        c2_high = c2.get('high', c2.get('close', 0))
        c3_low = c3.get('low', c3.get('open', 0))
        c3_high = c3.get('high', c3.get('close', 0))
        
        if c1.get('close', 0) > c2.get('open', 0) and c3.get('close', 0) < c2.get('open', 0):
            fvg_high = min(c1_high, c3_high)
            fvg_low = max(c1_low, c3_low)
            if fvg_high > fvg_low:
                return {
                    "type": "BEARISH_FVG",
                    "high": fvg_high,
                    "low": fvg_low,
                    "mid": (fvg_high + fvg_low) / 2
                }
        
        if c1.get('close', 0) < c2.get('open', 0) and c3.get('close', 0) > c2.get('open', 0):
            fvg_high = min(c1_high, c3_high)
            fvg_low = max(c1_low, c3_low)
            if fvg_high > fvg_low:
                return {
                    "type": "BULLISH_FVG",
                    "high": fvg_high,
                    "low": fvg_low,
                    "mid": (fvg_high + fvg_low) / 2
                }
    
    return None


def calculate_range_efficiency(candles: List[Dict], lookback: int = 20) -> float:
    if len(candles) < lookback:
        return 0.5
    
    recent = candles[-lookback:]
    
    total_range = 0
    trend_movement = 0
    
    for i in range(1, len(recent)):
        high = recent[i]["high"]
        low = recent[i]["low"]
        prev_high = recent[i-1]["high"]
        prev_low = recent[i-1]["low"]
        
        total_range += (high - low)
        
        if recent[i]["close"] > recent[i-1]["close"]:
            trend_movement += (recent[i]["close"] - recent[i-1]["close"])
        else:
            trend_movement -= (recent[i-1]["close"] - recent[i]["close"])
    
    if total_range == 0:
        return 0.5
    
    efficiency = abs(trend_movement) / total_range
    return min(efficiency, 1.0)


def is_chop_market(candles: List[Dict], threshold: float = 0.4) -> bool:
    efficiency = calculate_range_efficiency(candles)
    return efficiency < threshold


def get_liquidity_targets(candles: List[Dict], signal_type: str, lookback: int = 20) -> Dict:
    if len(candles) < 5:
        return {"target": None, "distance_pct": 0, "rr_ viable": False}
    
    swing_highs, swing_lows = detect_swing_levels(candles, lookback)
    
    current_price = candles[-1]["close"]
    atr = calculate_atr_from_candles(candles)
    
    if signal_type == "BUY":
        if not swing_lows:
            return {"target": None, "distance_pct": 0, "rr_viable": False}
        
        nearest_low = min(swing_lows)
        if nearest_low >= current_price:
            return {"target": None, "distance_pct": 0, "rr_viable": False}
        
        target = nearest_low
        distance_pct = abs(current_price - target) / current_price
        rr_viable = distance_pct < (atr / current_price * 3)
        
        return {"target": target, "distance_pct": distance_pct * 100, "rr_viable": rr_viable}
    
    else:
        if not swing_highs:
            return {"target": None, "distance_pct": 0, "rr_viable": False}
        
        nearest_high = max(swing_highs)
        if nearest_high <= current_price:
            return {"target": None, "distance_pct": 0, "rr_viable": False}
        
        target = nearest_high
        distance_pct = abs(current_price - target) / current_price
        rr_viable = distance_pct < (atr / current_price * 3)
        
        return {"target": target, "distance_pct": distance_pct * 100, "rr_viable": rr_viable}


def calculate_atr_from_candles(candles: List[Dict], period: int = 14) -> float:
    if len(candles) < period:
        return 0
    
    tr_values = []
    for i in range(1, min(len(candles), period + 1)):
        high = candles[-i]["high"]
        low = candles[-i]["low"]
        prev_close = candles[-i-1]["close"]
        
        tr = max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close)
        )
        tr_values.append(tr)
    
    return sum(tr_values) / len(tr_values) if tr_values else 0


def detect_liquidity_zones(candles: List[Dict], lookback: int = 50) -> Dict:
    if len(candles) < 10:
        return {"eqh": None, "eql": None, "highs": [], "lows": []}
    
    recent = candles[-lookback:] if len(candles) > lookback else candles
    
    swing_highs, swing_lows = detect_swing_levels(recent, lookback)
    
    highs_sorted = sorted(swing_highs, reverse=True)[:5]
    lows_sorted = sorted(swing_lows)[:5]
    
    eqh = max(swing_highs) if swing_highs else None
    eql = min(swing_lows) if swing_lows else None
    
    return {
        "eqh": eqh,
        "eql": eql,
        "highs": highs_sorted,
        "lows": lows_sorted
    }


def calculate_vwap(candles: List[Dict], lookback: int = 20) -> Optional[float]:
    if len(candles) < lookback:
        return None
    
    recent = candles[-lookback:]
    
    total_pv = 0
    total_volume = 0
    
    for candle in recent:
        typical_price = (candle["high"] + candle["low"] + candle["close"]) / 3
        volume = candle.get("volume", 1)
        
        total_pv += typical_price * volume
        total_volume += volume
    
    if total_volume == 0:
        return None
    
    return total_pv / total_volume


def get_vwap_bias(candles: List[Dict]) -> str:
    vwap = calculate_vwap(candles)
    if vwap is None:
        return "NEUTRAL"
    
    current_price = candles[-1]["close"]
    
    if current_price > vwap:
        return "BULLISH"
    elif current_price < vwap:
        return "BEARISH"
    return "NEUTRAL"
