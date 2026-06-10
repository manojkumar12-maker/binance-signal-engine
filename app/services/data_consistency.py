from typing import Dict, List, Tuple, Optional


def get_closed_candles(candles: List[Dict], remove_last: int = 1) -> List[Dict]:
    if not candles:
        return []
    
    return candles[:-remove_last] if remove_last > 0 else candles


def get_stable_candle_data(candles: List[Dict]) -> List[Dict]:
    return get_closed_candles(candles, remove_last=1)


def validate_candle_stability(candles: List[Dict], min_candles: int = 20) -> Tuple[bool, str]:
    if not candles or len(candles) < min_candles:
        return False, "INSUFFICIENT_CANDLES"
    
    if len(candles) < min_candles + 1:
        return True, "USING_CLOSED_ONLY"
    
    return True, "USING_CLOSED_CANDLES"


def get_consistent_data(candles: List[Dict], use_closed_only: bool = True) -> List[Dict]:
    if use_closed_only:
        return get_closed_candles(candles, remove_last=1)
    return candles


def extract_ohlcv(candles: List[Dict], include_volume: bool = True) -> List[Dict]:
    ohlcv = []
    for c in candles:
        candle = {
            "open": c.get("open"),
            "high": c.get("high"),
            "low": c.get("low"),
            "close": c.get("close")
        }
        if include_volume:
            candle["volume"] = c.get("volume", 0)
        ohlcv.append(candle)
    return ohlcv


def get_latest_closed_candle(candles: List[Dict]) -> Optional[Dict]:
    if not candles or len(candles) < 2:
        return None
    return candles[-2]


def is_candle_formative(candle: Dict, current_price: float, threshold: float = 0.001) -> bool:
    if not candle:
        return True
    
    close = candle.get("close", 0)
    if close <= 0:
        return True
    
    price_diff = abs(current_price - close) / close
    return price_diff < threshold


def detect_data_mismatch(candles_a: List[Dict], candles_b: List[Dict]) -> bool:
    if not candles_a or not candles_b:
        return False
    
    if len(candles_a) < 2 or len(candles_b) < 2:
        return False
    
    return candles_a[-2].get("close") != candles_b[-2].get("close")


def standardize_candle_input(candles: List[Dict]) -> Tuple[List[Dict], str]:
    if not candles:
        return [], "EMPTY"
    
    stable_candles = get_closed_candles(candles, remove_last=1)
    
    if len(stable_candles) < 20:
        return candles, "USE_ALL_AVAILABLE"
    
    return stable_candles, "USE_CLOSED_ONLY"
