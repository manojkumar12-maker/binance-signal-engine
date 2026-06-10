from typing import Dict, Tuple, List
import config
from app.services import volume


def calculate_bollinger_squeeze(candles: List[Dict], period: int = 20, std_dev: float = 2.0) -> Tuple[bool, float]:
    if not candles or len(candles) < period:
        return False, 0.0
    
    closes = [c['close'] for c in candles[-period:]]
    
    if not closes:
        return False, 0.0
    
    sma = sum(closes) / len(closes)
    variance = sum((x - sma) ** 2 for x in closes) / len(closes)
    std = variance ** 0.5
    
    current_price = candles[-1]['close']
    
    upper_band = sma + (std * std_dev)
    lower_band = sma - (std * std_dev)
    
    bandwidth = (upper_band - lower_band) / sma if sma > 0 else 1.0
    
    is_squeezed = bandwidth < config.VOLATILITY_COMPRESSION_THRESHOLD
    
    return is_squeezed, round(bandwidth, 4)


def calculate_atr_compression(candles: List[Dict], period: int = 14) -> Tuple[bool, float]:
    if not candles or len(candles) < period * 2:
        return False, 0.0
    
    current_atr = volume.calculate_atr(candles, period)
    
    older_candles = candles[-(period * 2):-period]
    older_atr = volume.calculate_atr(older_candles, period)
    
    if older_atr == 0:
        return False, 0.0
    
    atr_compression_ratio = current_atr / older_atr
    
    is_compressed = atr_compression_ratio < 0.6
    
    return is_compressed, round(atr_compression_ratio, 2)


def detect_volatility_compression(candles: List[Dict]) -> Tuple[bool, Dict]:
    if not candles or len(candles) < 50:
        return False, {}
    
    bb_squeezed, bb_width = calculate_bollinger_squeeze(candles)
    atr_compressed, atr_ratio = calculate_atr_compression(candles)
    
    is_compressed = bb_squeezed or atr_compressed
    
    details = {
        "bollinger_squeeze": bb_squeezed,
        "bollinger_width": bb_width,
        "atr_compression": atr_compressed,
        "atr_ratio": atr_ratio,
        "is_compressed": is_compressed,
        "compression_type": None
    }
    
    if bb_squeezed and atr_compressed:
        details["compression_type"] = "BB_ATR_COMPRESSION"
    elif bb_squeezed:
        details["compression_type"] = "BOLLINGER_SQUEEZE"
    elif atr_compressed:
        details["compression_type"] = "ATR_COMPRESSION"
    
    return is_compressed, details


def predict_breakout_direction(candles: List[Dict]) -> str:
    if not candles or len(candles) < 20:
        return "UNKNOWN"
    
    recent = candles[-20:]
    
    closes = [c['close'] for c in recent]
    opens = [c['open'] for c in recent]
    
    bullish_count = sum(1 for c, o in zip(closes, opens) if c > o)
    bearish_count = len(recent) - bullish_count
    
    if bullish_count > bearish_count:
        return "BULLISH_BREAKOUT"
    elif bearish_count > bullish_count:
        return "BEARISH_BREAKOUT"
    
    return "SIDEWAYS"


def get_compression_score(candles: List[Dict]) -> float:
    if not candles or len(candles) < 50:
        return 50.0
    
    is_compressed, details = detect_volatility_compression(candles)
    
    if is_compressed:
        score = 80.0
        
        if details.get("bollinger_width", 1) < 0.3:
            score += 10
        
        if details.get("atr_ratio", 1) < 0.4:
            score += 10
        
        return min(100, score)
    
    return 30.0


def is_breakout_imminent(candles: List[Dict]) -> Tuple[bool, str]:
    is_compressed, details = detect_volatility_compression(candles)
    
    if not is_compressed:
        return False, "NO_COMPRESSION"
    
    direction = predict_breakout_direction(candles)
    
    return True, direction
