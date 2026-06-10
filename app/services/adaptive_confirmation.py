import time
import config
from typing import Dict, Tuple, Optional


TIMEFRAME_DELAY_SECONDS = {
    "1m": 60,
    "5m": 120,
    "15m": 300,
    "30m": 600,
    "1h": 900,
    "2h": 1800,
    "4h": 3600,
    "6h": 5400,
    "12h": 10800,
    "1d": 21600
}


def get_confirmation_delay(timeframe: str, volatility_multiplier: float = 1.0) -> int:
    base_delay = TIMEFRAME_DELAY_SECONDS.get(timeframe, 900)
    
    adjusted_delay = base_delay * volatility_multiplier
    
    return int(adjusted_delay)


def get_volatility_multiplier(atr_ratio: float) -> float:
    if atr_ratio > 0.015:
        return 0.7
    elif atr_ratio > 0.008:
        return 0.85
    elif atr_ratio < 0.002:
        return 1.3
    return 1.0


def get_signal_max_age(timeframe: str) -> int:
    base_delay = TIMEFRAME_DELAY_SECONDS.get(timeframe, 900)
    return int(base_delay * 2)


def calculate_adaptive_confirmation(signal: Dict) -> Dict:
    timeframe = signal.get("timeframe", "1h")
    atr_ratio = signal.get("atr_ratio", 0.005)
    
    volatility_mult = get_volatility_multiplier(atr_ratio)
    confirmation_delay = get_confirmation_delay(timeframe, volatility_mult)
    max_age = get_signal_max_age(timeframe)
    
    return {
        "timeframe": timeframe,
        "confirmation_delay_seconds": confirmation_delay,
        "max_age_seconds": max_age,
        "volatility_multiplier": volatility_mult,
        "atr_ratio": atr_ratio
    }


def is_confirmation_ready(signal: Dict) -> Tuple[bool, str]:
    timeframe = signal.get("timeframe", "1h")
    atr_ratio = signal.get("atr_ratio", 0.005)
    
    volatility_mult = get_volatility_multiplier(atr_ratio)
    required_delay = get_confirmation_delay(timeframe, volatility_mult)
    
    locked_at = signal.get("locked_at", 0)
    if locked_at == 0:
        return False, "NO_TIMESTAMP"
    
    elapsed = time.time() - locked_at
    
    if elapsed < required_delay:
        remaining = required_delay - elapsed
        return False, f"WAITING {int(remaining)}s more"
    
    return True, "READY"


def is_signal_expired(signal: Dict) -> bool:
    timeframe = signal.get("timeframe", "1h")
    max_age = get_signal_max_age(timeframe)
    
    locked_at = signal.get("locked_at", 0)
    if locked_at == 0:
        return True
    
    elapsed = time.time() - locked_at
    return elapsed > max_age


def get_timeframe_seconds(tf: str) -> int:
    return TIMEFRAME_DELAY_SECONDS.get(tf, 900)
