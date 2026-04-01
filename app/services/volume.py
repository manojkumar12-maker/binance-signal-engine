from typing import List, Dict, Tuple


def calculate_atr(candles: List[Dict], period: int = 14) -> float:
    if len(candles) < period + 1:
        return 0.0
    
    true_ranges = []
    for i in range(1, len(candles)):
        high = candles[i]['high']
        low = candles[i]['low']
        prev_close = candles[i-1]['close']
        
        tr = max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close)
        )
        true_ranges.append(tr)
    
    if len(true_ranges) < period:
        return 0.0
    
    return sum(true_ranges[-period:]) / period


def get_atr_ratio(candles: List[Dict], current_price: float) -> float:
    atr = calculate_atr(candles)
    if current_price == 0:
        return 0.0
    return atr / current_price


def check_volume_confirmation(oi_data: List[float], candles: List[Dict]) -> Tuple[bool, bool]:
    if len(oi_data) < 5 or len(candles) < 5:
        return True, False
    
    recent_oi = oi_data[-5:]
    avg_oi = sum(recent_oi) / len(recent_oi)
    last_oi = oi_data[-1]
    
    last_candle = candles[-1]
    body = abs(last_candle['close'] - last_candle['open'])
    candle_range = last_candle['high'] - last_candle['low']
    
    oi_spike = last_oi > avg_oi * 1.4
    absorption = body < candle_range * 0.3 if candle_range > 0 else False
    
    return (oi_spike or absorption), oi_spike


def get_volume_strength(oi_data: List[float]) -> int:
    if len(oi_data) < 5:
        return 0
    
    recent_oi = oi_data[-5:]
    avg_oi = sum(recent_oi) / len(recent_oi)
    
    if oi_data[-1] > avg_oi * 1.4:
        return 20
    elif oi_data[-1] > avg_oi * 1.2:
        return 10
    
    return 0
