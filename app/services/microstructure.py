from typing import List, Dict, Tuple, Optional
from datetime import datetime
import logging
import config

logger = logging.getLogger("microstructure")

DELTA_WINDOW = 20
ABSORPTION_THRESHOLD = 0.25
L2_IMBALANCE_THRESHOLD = 0.65


def calculate_delta(candles: List[Dict]) -> float:
    if not candles or len(candles) < 3:
        return 0.0
    
    deltas = []
    recent = candles[-3:]
    
    for candle in recent:
        body = candle['close'] - candle['open']
        volume = candle.get('volume', 1)
        
        if candle['close'] > candle['open']:
            delta = volume
        elif candle['close'] < candle['open']:
            delta = -volume
        else:
            delta = 0
        
        deltas.append(delta)
    
    return sum(deltas) if deltas else 0.0


def calculate_delta_imbalance(candles: List[Dict]) -> Tuple[bool, float]:
    if not candles or len(candles) < DELTA_WINDOW:
        return False, 0.0
    
    recent = candles[-DELTA_WINDOW:]
    buy_volume = 0.0
    sell_volume = 0.0
    
    for candle in recent:
        volume = candle.get('volume', 1)
        if candle['close'] > candle['open']:
            buy_volume += volume
        elif candle['close'] < candle['open']:
            sell_volume += volume
    
    total = buy_volume + sell_volume
    if total == 0:
        return False, 0.0
    
    buy_ratio = buy_volume / total
    
    imbalance = abs(buy_ratio - 0.5) * 2
    
    is_imbalanced = imbalance > L2_IMBALANCE_THRESHOLD
    
    return is_imbalanced, round(imbalance, 2)


def detect_absorption(candles: List[Dict]) -> Tuple[bool, Dict]:
    if not candles or len(candles) < 5:
        return False, {"type": "NONE", "strength": 0}
    
    recent = candles[-5:]
    last = candles[-1]
    
    body = abs(last['close'] - last['open'])
    candle_range = last['high'] - last['low']
    
    if candle_range == 0:
        return False, {"type": "NONE", "strength": 0}
    
    body_ratio = body / candle_range
    
    if body_ratio < ABSORPTION_THRESHOLD:
        wick_top = last['high'] - max(last['close'], last['open'])
        wick_bottom = min(last['close'], last['open']) - last['low']
        
        if wick_top > wick_bottom and wick_top > candle_range * 0.5:
            return True, {"type": "SELL_ABSORPTION", "strength": round(1 - body_ratio, 2)}
        elif wick_bottom > wick_top and wick_bottom > candle_range * 0.5:
            return True, {"type": "BUY_ABSORPTION", "strength": round(1 - body_ratio, 2)}
    
    return False, {"type": "NONE", "strength": 0}


def detect_order_block(candles: List[Dict], direction: str) -> Optional[Dict]:
    if not candles or len(candles) < 10:
        return None
    
    recent = candles[-10:-1]
    
    if direction == "BUY":
        for i, candle in enumerate(recent):
            if candle['close'] < candle['open']:
                low = candle['low']
                if all(c['low'] >= low for c in recent[i+1:]):
                    return {
                        "price": low,
                        "type": "BUY_OB",
                        "candles_back": len(recent) - i
                    }
    else:
        for i, candle in enumerate(recent):
            if candle['close'] > candle['open']:
                high = candle['high']
                if all(c['high'] <= high for c in recent[i+1:]):
                    return {
                        "price": high,
                        "type": "SELL_OB",
                        "candles_back": len(recent) - i
                    }
    
    return None


def get_microstructure_score(candles: List[Dict], signal_direction: str) -> Dict:
    if not candles:
        return {
            "delta": 0,
            "delta_imbalance": False,
            "absorption": False,
            "order_block": None,
            "total_score": 50
        }
    
    delta = calculate_delta(candles)
    delta_imbalance, imbalance_strength = calculate_delta_imbalance(candles)
    absorption, absorption_details = detect_absorption(candles)
    order_block = detect_order_block(candles, signal_direction)
    
    score = 50
    
    if delta > 0 and signal_direction == "BUY":
        score += 10
    elif delta < 0 and signal_direction == "SELL":
        score += 10
    elif delta > 0 and signal_direction == "SELL":
        score -= 10
    elif delta < 0 and signal_direction == "BUY":
        score -= 10
    
    if delta_imbalance:
        score += 15
    
    if absorption:
        score += 10
    
    if order_block:
        score += 15
    
    return {
        "delta": delta,
        "delta_imbalance": delta_imbalance,
        "imbalance_strength": imbalance_strength,
        "absorption": absorption,
        "absorption_type": absorption_details.get("type"),
        "order_block": order_block,
        "total_score": min(100, max(0, score))
    }


def check_microstructure_entry(candles: List[Dict], signal_type: str, min_score: int = 60) -> Tuple[bool, str]:
    ms = get_microstructure_score(candles, signal_type)
    
    if ms["total_score"] >= min_score:
        return True, "MICROSTRUCTURE_OK"
    
    if ms["absorption"]:
        return True, "ABSORPTION_CONFIRMED"
    
    if ms["order_block"]:
        return True, "ORDER_BLOCK_FOUND"
    
    return False, f"MICROSTRUCTURE_WEAK ({ms['total_score']})"