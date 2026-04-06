from typing import Dict, Tuple, List
import config


def detect_pump_dump(candles: List[Dict], threshold: float = None) -> Tuple[bool, float]:
    if not candles or len(candles) < 20:
        return False, 0.0
    
    if threshold is None:
        threshold = config.NO_TRADE_PUMP_DUMP_THRESHOLD
    
    current_price = candles[-1]['close']
    price_20_candles_ago = candles[-20]['close']
    
    change_pct = abs(current_price - price_20_candles_ago) / price_20_candles_ago
    
    is_pump_dump = change_pct > threshold
    
    return is_pump_dump, round(change_pct * 100, 2)


def is_in_range_middle(candles: List[Dict], threshold: float = 0.5) -> Tuple[bool, float]:
    if not candles or len(candles) < 20:
        return False, 0.0
    
    recent_highs = [c['high'] for c in candles[-20:]]
    recent_lows = [c['low'] for c in candles[-20:]]
    
    range_high = max(recent_highs)
    range_low = min(recent_lows)
    range_size = range_high - range_low
    
    if range_size == 0:
        return False, 0.0
    
    current_price = candles[-1]['close']
    position_in_range = (current_price - range_low) / range_size
    
    is_middle = threshold - 0.15 < position_in_range < threshold + 0.15
    
    return is_middle, round(position_in_range, 2)


def check_no_trade_zones(candles: List[Dict]) -> Tuple[bool, Dict]:
    if not candles or len(candles) < 20:
        return False, {"status": "NO_DATA"}
    
    is_pump, pump_pct = detect_pump_dump(candles)
    is_middle, position = is_in_range_middle(candles)
    
    is_no_trade = is_pump or is_middle
    
    details = {
        "is_no_trade": is_no_trade,
        "pump_dump_detected": is_pump,
        "pump_dump_pct": pump_pct,
        "range_middle_detected": is_middle,
        "position_in_range": position,
        "status": "NO_TRADE" if is_no_trade else "CLEAR"
    }
    
    return is_no_trade, details


def get_zone_status(candles: List[Dict]) -> str:
    is_no_trade, details = check_no_trade_zones(candles)
    return details.get("status", "UNKNOWN")


def is_trade_allowed(candles: List[Dict]) -> Tuple[bool, str]:
    is_no_trade, details = check_no_trade_zones(candles)
    
    if not is_no_trade:
        return True, "CLEAR"
    
    if details.get("pump_dump_detected"):
        return False, f"PUMP_DUMP_DETECTED ({details['pump_dump_pct']}%)"
    
    if details.get("range_middle_detected"):
        return False, f"RANGE_MIDDLE (position: {details['position_in_range']})"
    
    return False, "UNKNOWN_ZONE"
