from typing import Dict, Tuple, List
import config


def calculate_wick_to_body_ratio(candle: Dict) -> float:
    body = abs(candle['close'] - candle['open'])
    upper_wick = candle['high'] - max(candle['close'], candle['open'])
    lower_wick = min(candle['close'], candle['open']) - candle['low']
    
    if body == 0:
        return 0.0
    
    total_wick = upper_wick + lower_wick
    return total_wick / body


def detect_volume_divergence(candles: List[Dict], breakout_index: int = -1) -> Tuple[bool, float]:
    if not candles or len(candles) < 20:
        return False, 0.0
    
    recent_volumes = [c.get('volume', 0) for c in candles[-20:-1]]
    breakout_volume = candles[breakout_index].get('volume', 0)
    
    if not recent_volumes or sum(recent_volumes) == 0:
        return False, 0.0
    
    avg_volume = sum(recent_volumes) / len(recent_volumes)
    volume_ratio = breakout_volume / avg_volume if avg_volume > 0 else 1.0
    
    is_divergence = volume_ratio < 0.5
    
    return is_divergence, round(volume_ratio, 2)


def calculate_delta_imbalance(candles: List[Dict]) -> Tuple[bool, float]:
    if not candles or len(candles) < 10:
        return False, 0.0
    
    last = candles[-1]
    prev = candles[-2]
    
    last_close = last['close']
    last_open = last['open']
    prev_close = prev['close']
    prev_open = prev['open']
    
    last_direction = 1 if last_close > last_open else -1
    prev_direction = 1 if prev_close > prev_open else -1
    
    is_imbalance = last_direction != prev_direction
    
    last_strength = abs(last_close - last_open) / (last['high'] - last['low']) if last['high'] != last['low'] else 0
    prev_strength = abs(prev_close - prev_open) / (prev['high'] - prev['low']) if prev['high'] != prev['low'] else 0
    
    strength_change = abs(last_strength - prev_strength)
    
    return is_imbalance, round(strength_change, 2)


def detect_fake_breakout_trap(candles: List[Dict]) -> Tuple[bool, Dict]:
    if not candles or len(candles) < 20:
        return False, {}
    
    last = candles[-1]
    prev = candles[-2]
    recent_highs = [c['high'] for c in candles[-20:-1]]
    recent_volumes = [c.get('volume', 1) for c in candles[-20:-1]]
    
    highest_high = max(recent_highs)
    
    is_breakout = last['high'] > highest_high
    
    wick_ratio = calculate_wick_to_body_ratio(last)
    high_wick = wick_ratio > 2.0
    
    is_vol_div, vol_ratio = detect_volume_divergence(candles, -1)
    
    is_delta_imbalance, delta_strength = calculate_delta_imbalance(candles)
    
    rejection = last['close'] < prev['close'] and last['high'] > highest_high
    
    is_trap = (
        is_breakout and (
            high_wick or
            is_vol_div or
            rejection or
            is_delta_imbalance
        )
    )
    
    details = {
        "is_breakout": is_breakout,
        "high_wick": high_wick,
        "wick_ratio": round(wick_ratio, 2),
        "volume_divergence": is_vol_div,
        "volume_ratio": vol_ratio,
        "rejection": rejection,
        "delta_imbalance": is_delta_imbalance,
        "is_fake_breakout_trap": is_trap
    }
    
    return is_trap, details


def filter_breakout_signals(candles: List[Dict]) -> Tuple[bool, str]:
    is_trap, details = detect_fake_breakout_trap(candles)
    
    if is_trap:
        if details.get("high_wick"):
            return False, "HIGH_WICK_REJECTION"
        elif details.get("volume_divergence"):
            return False, "LOW_VOLUME_BREAKOUT"
        elif details.get("rejection"):
            return False, "PRICE_REJECTION"
        elif details.get("delta_imbalance"):
            return False, "DELTA_REVERSAL"
    
    return True, "VALID_BREAKOUT"


def get_breakout_quality(candles: List[Dict]) -> float:
    if not candles or len(candles) < 20:
        return 50.0
    
    is_trap, details = detect_fake_breakout_trap(candles)
    
    if is_trap:
        return 0.0
    
    score = 100.0
    
    if details.get("volume_ratio", 1) < 1.0:
        score -= 20
    
    if details.get("wick_ratio", 0) > 1.5:
        score -= 15
    
    return max(0, score)
