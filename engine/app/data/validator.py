import time
from typing import List, Dict, Optional, Any

MAX_CANDLE_AGE_MS = 120000


def validate_candles(candles: Any) -> bool:
    if not candles or not isinstance(candles, list) or len(candles) < 20:
        return False
    
    for c in candles[-5:]:
        if not isinstance(c, dict):
            return False
        if any(v is None for v in c.values()):
            return False
    
    return True


def is_fresh(candles: Any) -> bool:
    if not candles or not isinstance(candles, list) or not candles:
        return False
    
    last_ts = candles[-1].get('timestamp', 0)
    now = int(time.time() * 1000)
    
    return (now - last_ts) < MAX_CANDLE_AGE_MS


def is_volatile(candles: Any, min_atr_pct: float = 0.002) -> bool:
    if not candles or not isinstance(candles, list) or len(candles) < 14:
        return True
    
    atr = calculate_atr(candles)
    price = candles[-1].get('close', 0)
    
    if price == 0:
        return True
    
    return (atr / price) > min_atr_pct


def calculate_atr(candles: List[Dict], period: int = 14) -> float:
    if len(candles) < period + 1:
        return 0
    
    tr_values = []
    for i in range(1, min(len(candles), period + 1)):
        high = candles[-i].get('high', 0)
        low = candles[-i].get('low', 0)
        prev_close = candles[-i-1].get('close', 0)
        
        tr = max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close)
        )
        tr_values.append(tr)
    
    if not tr_values:
        return 0
    
    return sum(tr_values) / len(tr_values)


def select_active_pairs(pairs: List[str], cache: dict, min_move_pct: float = 0.003) -> List[str]:
    selected = []
    
    for p in pairs:
        candles = cache.get(p)
        
        if not candles or len(candles) < 2:
            continue
        
        last = candles[-1]
        prev = candles[-2]
        
        prev_close = prev.get('close', 0)
        if prev_close == 0:
            continue
        
        move = abs(last.get('close', 0) - prev_close) / prev_close
        
        if move > min_move_pct:
            selected.append(p)
    
    return selected[:100]


def get_pair_cache() -> dict:
    from core.redis_client import get_data
    
    cache = {}
    from core.config import PAIRS
    
    for pair in PAIRS:
        candles = get_data(f"{pair}:1h")
        if candles:
            cache[pair] = candles
    
    return cache
