import time
import json
from typing import Dict, Optional, List, Union, Any
from datetime import datetime
import config


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


def get_redis_client():
    try:
        from app.services import redis_client as rc
        if rc.r:
            rc.r.ping()
            return rc.r
        return None
    except:
        return None


def acquire_lock(symbol: str, ttl: int = 10) -> bool:
    r = get_redis_client()
    if not r:
        return True
    
    lock_key = f"lock:{symbol}"
    return r.set(lock_key, "1", nx=True, ex=ttl)


def release_lock(symbol: str) -> bool:
    r = get_redis_client()
    if not r:
        return True
    
    lock_key = f"lock:{symbol}"
    r.delete(lock_key)
    return True


def store_signal(signal: Dict, state: str = "PENDING") -> Optional[Dict]:
    pair = signal.get("pair")
    if not pair:
        return signal
    
    if not acquire_lock(pair):
        return None
    
    r = get_redis_client()
    
    existing_key = f"signal:{pair}"
    if r:
        existing = r.get(existing_key)
        if existing:
            release_lock(pair)
            return json.loads(existing)
    
    locked_signal = signal.copy()
    locked_signal["signal_state"] = state
    locked_signal["locked_at"] = time.time()
    locked_signal["locked_timestamp"] = datetime.utcnow().isoformat()
    locked_signal["ttl"] = config.SIGNAL_DECAY_MINUTES * 60
    
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
    
    if r:
        r.set(existing_key, json.dumps(locked_signal), ex=locked_signal["ttl"])
        
        verification = r.get(existing_key)
        if not verification:
            release_lock(pair)
            return None
    
    release_lock(pair)
    return locked_signal


def get_stored_signal(pair: str) -> Optional[Dict]:
    r = get_redis_client()
    if not r:
        return None
    
    key = f"signal:{pair}"
    data = r.get(key)
    if data:
        return json.loads(data)
    return None


def is_signal_locked(pair: str) -> bool:
    r = get_redis_client()
    if not r:
        return False
    
    key = f"signal:{pair}"
    return r.exists(key) > 0


def update_signal_state(pair: str, new_state: str, reason: str = "") -> bool:
    if not acquire_lock(pair):
        return False
    
    r = get_redis_client()
    if not r:
        release_lock(pair)
        return False
    
    key = f"signal:{pair}"
    
    data = r.get(key)
    if not data:
        release_lock(pair)
        return False
    
    signal = json.loads(data)
    signal["signal_state"] = new_state
    signal["state_updated_at"] = time.time()
    
    if reason:
        signal["state_reason"] = reason
    
    r.set(key, json.dumps(signal), ex=signal.get("ttl", 1800))
    
    release_lock(pair)
    return True


def confirm_signal(pair: str) -> bool:
    return update_signal_state(pair, SIGNAL_STATES["CONFIRMED"], "passed_validation")


def execute_signal(pair: str) -> bool:
    return update_signal_state(pair, SIGNAL_STATES["EXECUTED"], "trade_executed")


def close_signal(pair: str) -> bool:
    return update_signal_state(pair, SIGNAL_STATES["CLOSED"], "trade_closed")


def reject_signal(pair: str, reason: str = "") -> bool:
    return update_signal_state(pair, SIGNAL_STATES["REJECTED"], reason)


def expire_signal(pair: str) -> bool:
    return update_signal_state(pair, SIGNAL_STATES["EXPIRED"], "expired")


def validate_stored_signal(pair: str, min_confidence: float = 65) -> tuple[bool, str]:
    signal = get_stored_signal(pair)
    
    if not signal:
        return False, "NO_STORED_SIGNAL"
    
    state = signal.get("signal_state")
    if state in [SIGNAL_STATES["EXECUTED"], SIGNAL_STATES["CLOSED"], SIGNAL_STATES["REJECTED"], SIGNAL_STATES["EXPIRED"]]:
        return False, f"SIGNAL_STATE_{state}"
    
    locked_at = signal.get("locked_at", 0)
    decay_time = signal.get("ttl", 1800)
    
    if time.time() - locked_at > decay_time:
        expire_signal(pair)
        return False, "SIGNAL_EXPIRED"
    
    confidence = signal.get("confidence", 0)
    if confidence < min_confidence:
        return False, f"LOW_CONFIDENCE_{confidence}"
    
    return True, "VALID"


def revalidate_signal(pair: str, new_signal: Dict, min_confidence: float = 65) -> tuple[bool, str]:
    stored = get_stored_signal(pair)
    
    if not stored:
        return False, "NO_STORED_SIGNAL"
    
    stored_confidence = stored.get("confidence", 0)
    new_confidence = new_signal.get("confidence", 0)
    
    confidence_drop = stored_confidence - new_confidence
    
    if confidence_drop > 20:
        return False, f"CONFIDENCE_DROPPED_{confidence_drop}"
    
    stored_entry = stored.get("entry_primary", 0)
    new_entry = new_signal.get("entry_primary", 0)
    
    if stored_entry > 0 and new_entry > 0:
        entry_change = abs(new_entry - stored_entry) / stored_entry
        if entry_change > 0.01:
            return False, f"ENTRY_CHANGED_{round(entry_change * 100, 2)}%"
    
    if new_confidence < min_confidence:
        return False, f"NEW_LOW_CONFIDENCE_{new_confidence}"
    
    return True, "VALID"


def get_all_stored_signals(state: Optional[str] = None) -> List[Dict]:
    r = get_redis_client()
    if not r:
        return []
    
    keys = r.keys("signal:*")
    keys_list: List[Any] = list(keys) if keys else []
    if not keys_list:
        return []
    
    signals: List[Dict] = []
    
    for key in keys_list:
        key_str = str(key) if key else None
        if not key_str:
            continue
        data = r.get(key_str)
        if data:
            signal = json.loads(data)
            if state is None or signal.get("signal_state") == state:
                signals.append(signal)
    
    return signals


def get_signals_for_trading() -> List[Dict]:
    return get_all_stored_signals(SIGNAL_STATES["PENDING"]) + get_all_stored_signals(SIGNAL_STATES["CONFIRMED"])


def clear_expired_signals() -> int:
    r = get_redis_client()
    if not r:
        return 0
    
    keys = r.keys("signal:*")
    keys_list: List[Any] = list(keys) if keys else []
    if not keys_list:
        return 0
    
    cleared = 0
    
    for key in keys_list:
        key_str = str(key) if key else None
        if not key_str:
            continue
        data = r.get(key_str)
        if data:
            signal = json.loads(data)
            state = signal.get("signal_state")
            if state in [SIGNAL_STATES["EXPIRED"], SIGNAL_STATES["REJECTED"], SIGNAL_STATES["CLOSED"]]:
                r.delete(key)
                cleared += 1
    
    return cleared


def get_signal_snapshot(pair: str) -> Optional[Dict]:
    signal = get_stored_signal(pair)
    if not signal:
        return None
    
    return signal.get("snapshot")


def get_signal_display(pair: str) -> Dict:
    signal = get_stored_signal(pair)
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
