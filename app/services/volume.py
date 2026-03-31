from typing import List, Dict


def check_volume_confirmation(oi_data: List[float], candles: List[Dict]) -> bool:
    if len(oi_data) < 5 or len(candles) < 5:
        return True
    
    recent_oi = oi_data[-5:]
    avg_oi = sum(recent_oi) / len(recent_oi)
    last_oi = oi_data[-1]
    
    last_candle = candles[-1]
    body = abs(last_candle['close'] - last_candle['open'])
    candle_range = last_candle['high'] - last_candle['low']
    
    oi_spike = last_oi > avg_oi * 1.4
    absorption = body < candle_range * 0.3 if candle_range > 0 else False
    
    return oi_spike or absorption


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
