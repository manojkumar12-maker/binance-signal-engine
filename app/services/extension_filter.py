from typing import Dict, Tuple
import config


def calculate_ema(candles: list, period: int = 25) -> float:
    if len(candles) < period:
        return 0
    
    closes = [c['close'] for c in candles]
    ema = sum(closes[:period]) / period
    
    multiplier = 2 / (period + 1)
    for price in closes[period:]:
        ema = (price - ema) * multiplier + ema
    
    return ema


def calculate_ema25(candles: list) -> float:
    return calculate_ema(candles, 25)


def check_extension(candles: list, timeframe: str = "1h") -> Tuple[bool, float]:
    if not candles or len(candles) < 50:
        return True, 0.0
    
    current_price = candles[-1]['close']
    
    ema25 = calculate_ema25(candles)
    ema50 = calculate_ema(candles, 50)
    
    if ema25 == 0:
        return True, 0.0
    
    ema_distance = abs(current_price - ema25) / ema25
    
    threshold = config.EXTENSION_FILTER_1H if timeframe == "1h" else config.EXTENSION_FILTER_4H
    
    is_extended = ema_distance > threshold
    
    return is_extended, round(ema_distance * 100, 2)


def check_extension_multi_tf(candles_1h: list, candles_4h: list) -> Tuple[bool, Dict]:
    extended_1h, distance_1h = check_extension(candles_1h, "1h")
    extended_4h, distance_4h = check_extension(candles_4h, "4h")
    
    return extended_1h or extended_4h, {
        "1h_extended": extended_1h,
        "1h_distance_pct": distance_1h,
        "4h_extended": extended_4h,
        "4h_distance_pct": distance_4h,
        "threshold_1h": config.EXTENSION_FILTER_1H * 100,
        "threshold_4h": config.EXTENSION_FILTER_4H * 100
    }


def get_distance_from_ema(candles: list, ema_period: int = 25) -> float:
    if len(candles) < ema_period:
        return 0.0
    
    current_price = candles[-1]['close']
    ema = calculate_ema(candles, ema_period)
    
    if ema == 0:
        return 0.0
    
    return (current_price - ema) / ema
