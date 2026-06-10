from typing import Dict, Tuple
import config


def find_nearest_support(candles: list, current_price: float) -> float:
    if not candles or len(candles) < 20:
        return 0
    
    lows = [c['low'] for c in candles[-50:]]
    supports = [low for low in lows if low < current_price]
    
    if not supports:
        return 0
    
    nearest = max(supports)
    return nearest


def find_nearest_resistance(candles: list, current_price: float) -> float:
    if not candles or len(candles) < 20:
        return 0
    
    highs = [c['high'] for c in candles[-50:]]
    resistances = [high for high in highs if high > current_price]
    
    if not resistances:
        return 0
    
    nearest = min(resistances)
    return nearest


def calculate_support_score(candles: list, signal: str) -> float:
    if not candles:
        return 50
    
    current_price = candles[-1]['close']
    nearest_support = find_nearest_support(candles, current_price)
    nearest_resistance = find_nearest_resistance(candles, current_price)
    
    if signal == "BUY":
        if nearest_support == 0:
            return 70
        distance_to_support = abs(current_price - nearest_support) / current_price
        if distance_to_support < 0.02:
            return 95
        elif distance_to_support < 0.05:
            return 80
        elif distance_to_support < 0.10:
            return 60
        else:
            return 40
    else:
        if nearest_resistance == 0:
            return 70
        distance_to_resistance = abs(current_price - nearest_resistance) / current_price
        if distance_to_resistance < 0.02:
            return 95
        elif distance_to_resistance < 0.05:
            return 80
        elif distance_to_resistance < 0.10:
            return 60
        else:
            return 40


def calculate_rr_ratio(entry: float, sl: float, tp: float, signal: str) -> float:
    if entry <= 0 or sl <= 0 or tp <= 0:
        return 0
    
    if signal == "BUY":
        risk = entry - sl
        reward = tp - entry
    else:
        risk = sl - entry
        reward = entry - tp
    
    if risk == 0:
        return 0
    
    return reward / risk


def calculate_rr_score(entry: float, sl: float, tp1: float, signal: str) -> float:
    rr = calculate_rr_ratio(entry, sl, tp1, signal)
    
    if rr >= config.MIN_RR_RATIO * 2:
        return 100
    elif rr >= config.MIN_RR_RATIO:
        return 80
    elif rr >= 1.0:
        return 60
    elif rr >= 0.5:
        return 40
    else:
        return 20


def check_liquidity_position(candles: list, signal: str) -> float:
    if not candles or len(candles) < 20:
        return 50
    
    current_price = candles[-1]['close']
    
    recent_highs = [c['high'] for c in candles[-20:]]
    recent_lows = [c['low'] for c in candles[-20:]]
    
    if signal == "BUY":
        below_recent_low = current_price < min(recent_lows)
        near_low = current_price - min(recent_lows) < current_price * 0.02
        
        if below_recent_low:
            return 95
        elif near_low:
            return 85
        else:
            return 50
    else:
        above_recent_high = current_price > max(recent_highs)
        near_high = max(recent_highs) - current_price < current_price * 0.02
        
        if above_recent_high:
            return 95
        elif near_high:
            return 85
        else:
            return 50


def calculate_entry_quality_score(
    candles: list,
    signal: str,
    entry: float,
    sl: float,
    tp1: float
) -> Tuple[float, Dict]:
    if not candles or entry <= 0 or sl <= 0:
        return 0, {"support_score": 0, "rr_score": 0, "liquidity_score": 0, "total": 0}
    
    support_score = calculate_support_score(candles, signal)
    rr_score = calculate_rr_score(entry, sl, tp1, signal)
    liquidity_score = check_liquidity_position(candles, signal)
    
    total = (support_score * 0.35) + (rr_score * 0.35) + (liquidity_score * 0.30)
    
    breakdown = {
        "support_score": support_score,
        "rr_score": rr_score,
        "liquidity_score": liquidity_score,
        "total": round(total, 2)
    }
    
    return round(total, 2), breakdown


def is_good_entry(entry_score: float) -> bool:
    return entry_score >= config.ENTRY_QUALITY_THRESHOLD
