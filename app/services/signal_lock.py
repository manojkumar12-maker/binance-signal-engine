import time
import json
from typing import Dict, Optional, List
from datetime import datetime


SIGNAL_LOCK_STORE = {}


SIGNAL_STATES = {
    "PENDING": "PENDING",
    "CONFIRMED": "CONFIRMED", 
    "EXECUTED": "EXECUTED",
    "CLOSED": "CLOSED",
    "EXPIRED": "EXPIRED",
    "REJECTED": "REJECTED"
}


SIGNAL_DECAY_SECONDS = {
    "15m": 900,
    "1h": 1800,
    "4h": 7200
}


def lock_signal(signal: Dict, state: str = "PENDING") -> Dict:
    pair = signal.get("pair")
    if not pair:
        return signal
    
    locked_signal = signal.copy()
    
    locked_signal["signal_state"] = state
    locked_signal["locked_at"] = time.time()
    locked_signal["locked_timestamp"] = datetime.utcnow().isoformat()
    
    locked_signal["snapshot"] = {
        "trend": signal.get("trend"),
        "volume": signal.get("volume"),
        "liquidity": signal.get("liquidity"),
        "regime": signal.get("regime"),
        "whale_signal": signal.get("whale_signal"),
        "market_bias": signal.get("market_bias"),
        "is_reversal": signal.get("is_reversal"),
        "fake_breakout": signal.get("fake_breakout"),
        "atr_ratio": signal.get("atr_ratio"),
        "entry_score": signal.get("entry_score")
    }
    
    SIGNAL_LOCK_STORE[pair] = locked_signal
    
    return locked_signal


def get_locked_signal(pair: str) -> Optional[Dict]:
    return SIGNAL_LOCK_STORE.get(pair)


def is_signal_locked(pair: str) -> bool:
    return pair in SIGNAL_LOCK_STORE


def get_signal_state(pair: str) -> str:
    signal = get_locked_signal(pair)
    if not signal:
        return None
    return signal.get("signal_state")


def update_signal_state(pair: str, new_state: str) -> bool:
    if pair not in SIGNAL_LOCK_STORE:
        return False
    
    SIGNAL_LOCK_STORE[pair]["signal_state"] = new_state
    SIGNAL_LOCK_STORE[pair]["state_updated_at"] = time.time()
    return True


def confirm_signal(pair: str) -> bool:
    return update_signal_state(pair, SIGNAL_STATES["CONFIRMED"])


def execute_signal(pair: str) -> bool:
    return update_signal_state(pair, SIGNAL_STATES["EXECUTED"])


def close_signal(pair: str) -> bool:
    return update_signal_state(pair, SIGNAL_STATES["CLOSED"])


def reject_signal(pair: str, reason: str = "") -> bool:
    if pair not in SIGNAL_LOCK_STORE:
        return False
    
    SIGNAL_LOCK_STORE[pair]["signal_state"] = SIGNAL_STATES["REJECTED"]
    SIGNAL_LOCK_STORE[pair]["reject_reason"] = reason
    return True


def expire_signal(pair: str) -> bool:
    return update_signal_state(pair, SIGNAL_STATES["EXPIRED"])


def is_signal_expired(pair: str, timeframe: str = "1h") -> bool:
    signal = get_locked_signal(pair)
    if not signal:
        return True
    
    decay_time = SIGNAL_DECAY_SECONDS.get(timeframe, 1800)
    locked_at = signal.get("locked_at", 0)
    
    if time.time() - locked_at > decay_time:
        expire_signal(pair)
        return True
    
    return False


def validate_locked_signal(pair: str, min_confidence: float = 65) -> tuple[bool, str]:
    signal = get_locked_signal(pair)
    
    if not signal:
        return False, "NO_LOCKED_SIGNAL"
    
    state = signal.get("signal_state")
    if state in [SIGNAL_STATES["EXECUTED"], SIGNAL_STATES["CLOSED"], SIGNAL_STATES["REJECTED"], SIGNAL_STATES["EXPIRED"]]:
        return False, f"SIGNAL_STATE_{state}"
    
    if is_signal_expired(pair):
        return False, "SIGNAL_EXPIRED"
    
    confidence = signal.get("confidence", 0)
    if confidence < min_confidence:
        return False, f"LOW_CONFIDENCE_{confidence}"
    
    return True, "VALID"


def revalidate_signal(pair: str, new_signal: Dict, min_confidence: float = 65) -> tuple[bool, str]:
    locked = get_locked_signal(pair)
    
    if not locked:
        return False, "NO_LOCKED_SIGNAL"
    
    locked_confidence = locked.get("confidence", 0)
    new_confidence = new_signal.get("confidence", 0)
    
    confidence_drop = locked_confidence - new_confidence
    
    if confidence_drop > 20:
        return False, f"CONFIDENCE_DROPPED_{confidence_drop}"
    
    locked_entry = locked.get("entry_primary", 0)
    new_entry = new_signal.get("entry_primary", 0)
    
    if locked_entry > 0 and new_entry > 0:
        entry_change = abs(new_entry - locked_entry) / locked_entry
        if entry_change > 0.01:
            return False, f"ENTRY_CHANGED_{round(entry_change * 100, 2)}%"
    
    new_confidence = new_signal.get("confidence", 0)
    if new_confidence < min_confidence:
        return False, f"NEW_LOW_CONFIDENCE_{new_confidence}"
    
    return True, "VALID"


def get_all_locked_signals(state: str = None) -> List[Dict]:
    signals = list(SIGNAL_LOCK_STORE.values())
    
    if state:
        signals = [s for s in signals if s.get("signal_state") == state]
    
    return signals


def get_locked_signals_for_trading() -> List[Dict]:
    return get_all_locked_signals(SIGNAL_STATES["PENDING"]) + get_all_locked_signals(SIGNAL_STATES["CONFIRMED"])


def clear_expired_signals():
    pairs_to_clear = []
    
    for pair, signal in SIGNAL_LOCK_STORE.items():
        state = signal.get("signal_state")
        if state in [SIGNAL_STATES["EXPIRED"], SIGNAL_STATES["REJECTED"], SIGNAL_STATES["CLOSED"]]:
            pairs_to_clear.append(pair)
    
    for pair in pairs_to_clear:
        SIGNAL_LOCK_STORE.pop(pair, None)
    
    return len(pairs_to_clear)


def get_signal_snapshot(pair: str) -> Optional[Dict]:
    signal = get_locked_signal(pair)
    if not signal:
        return None
    
    return signal.get("snapshot")


def get_locked_signal_display(pair: str) -> Dict:
    signal = get_locked_signal(pair)
    if not signal:
        return {"pair": pair, "status": "NO_SIGNAL"}
    
    return {
        "pair": pair,
        "signal": signal.get("signal"),
        "confidence": signal.get("confidence"),
        "entry": signal.get("entry_primary"),
        "state": signal.get("signal_state"),
        "locked_at": signal.get("locked_timestamp"),
        "age_seconds": time.time() - signal.get("locked_at", 0)
    }
