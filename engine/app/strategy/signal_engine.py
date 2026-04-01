from typing import Dict, List, Optional
from datetime import datetime
from core.config import (
    PAIRS, SL_PERCENT, TP1_PERCENT, TP2_PERCENT, TP3_PERCENT, MIN_CONFIDENCE
)
from core.redis_client import get_data
from data.candle_builder import build_4h
from data.oi_fetcher import register_active_pair
from data.validator import validate_candles, is_fresh, is_volatile
import logging

logger = logging.getLogger(__name__)

LAST_SIGNALS = {}


def is_new_signal(signal: Dict) -> bool:
    key = signal['pair']
    if key in LAST_SIGNALS:
        if LAST_SIGNALS[key] == signal['signal']:
            return False
    LAST_SIGNALS[key] = signal['signal']
    return True


def detect_trend(candles: List[Dict]) -> str:
    if len(candles) < 5:
        return "RANGE"
    
    recent = candles[-5:]
    highs = [c["high"] for c in recent]
    lows = [c["low"] for c in recent]
    
    ch = highs[-1], ph = highs[-2], sph = highs[-3]
    cl = lows[-1], pl = lows[-2], spl = lows[-3]
    
    if ch > ph and ch > sph and cl > pl and cl > spl:
        return "UPTREND"
    if ch < ph and ch < sph and cl < pl and cl < spl:
        return "DOWNTREND"
    return "RANGE"


def candle_strength(candle: Dict) -> int:
    body = abs(candle.get('close', 0) - candle.get('open', 0))
    range_ = candle.get('high', 0) - candle.get('low', 0)
    if range_ == 0:
        return 0
    return int((body / range_) * 20)


def detect_sweep(candles: List[Dict]) -> Optional[str]:
    if len(candles) < 20:
        return None
    
    recent = candles[-20:-1]
    last = candles[-1]
    
    swing_highs = []
    swing_lows = []
    
    for i in range(1, len(recent) - 1):
        if recent[i]["high"] > recent[i-1]["high"] and recent[i]["high"] > recent[i+1]["high"]:
            swing_highs.append(recent[i]["high"])
        if recent[i]["low"] < recent[i-1]["low"] and recent[i]["low"] < recent[i+1]["low"]:
            swing_lows.append(recent[i]["low"])
    
    if not swing_highs or not swing_lows:
        return None
    
    recent_high = max(swing_highs[-5:]) if len(swing_highs) >= 5 else max(swing_highs)
    recent_low = min(swing_lows[-5:]) if len(swing_lows) >= 5 else min(swing_lows)
    
    lh, ll, lc = last["high"], last["low"], last["close"]
    
    if lh > recent_high:
        if lc < recent_high:
            return "SWEEP_HIGH_REJECTION"
        return "SWEEP_HIGH"
    if ll < recent_low:
        if lc > recent_low:
            return "SWEEP_LOW_REJECTION"
        return "SWEEP_LOW"
    return None


def align_sweep(trend: str, sweep: Optional[str]) -> bool:
    if not sweep:
        return False
    if trend == "UPTREND" and sweep in ["SWEEP_LOW", "SWEEP_LOW_REJECTION"]:
        return True
    if trend == "DOWNTREND" and sweep in ["SWEEP_HIGH", "SWEEP_HIGH_REJECTION"]:
        return True
    return False


def check_volume(oi: float, oi_history: List[float], candles: List[Dict]) -> bool:
    if len(oi_history) < 5 or not candles:
        return True
    
    avg_oi = sum(oi_history[-5:]) / 5
    oi_spike = oi > avg_oi * 1.4
    
    last = candles[-1]
    body = abs(last.get('close', 0) - last.get('open', 0))
    range_ = last.get('high', 0) - last.get('low', 0)
    absorption = body < range_ * 0.3 if range_ > 0 else False
    
    return True


def get_volume_score(oi: float, oi_history: List[float], candles: List[Dict]) -> int:
    if len(oi_history) < 5 or not candles:
        return 5
    
    avg_oi = sum(oi_history[-5:]) / 5
    oi_spike = oi > avg_oi * 1.4
    
    last = candles[-1]
    body = abs(last.get('close', 0) - last.get('open', 0))
    range_ = last.get('high', 0) - last.get('low', 0)
    absorption = body < range_ * 0.3 if range_ > 0 else False
    
    if oi_spike or absorption:
        return 20
    return 5


def calculate_confidence(trend: str, sweep: Optional[str], volume: bool, strength: int = 0, 
                        htf_aligned: bool = True, is_reversal: bool = False) -> int:
    score = 50
    
    if trend != "RANGE":
        score += 20
    else:
        score -= 5
    
    if htf_aligned:
        score += 15
    else:
        if sweep and "REJECTION" in sweep:
            score += 5
        else:
            score -= 5
    
    if sweep:
        if "REJECTION" in sweep:
            score += 25
        else:
            score += 15
    else:
        score -= 5
    
    if volume:
        score += 20
    else:
        score += 5
    
    score += min(strength, 15)
    
    if is_reversal:
        score += 15
    
    return max(0, min(score, 100))


def detect_reversal(candles: List[Dict], sweep_type: Optional[str]) -> bool:
    if not sweep_type or "REJECTION" not in sweep_type:
        if len(candles) >= 2:
            last = candles[-1]
            prev = candles[-2]
            if abs(last['close'] - prev['close']) / prev['close'] > 0.008:
                return True
        return False
    
    if len(candles) < 2:
        return True
    
    last = candles[-1]
    prev = candles[-2]
    
    if sweep_type == "SWEEP_LOW_REJECTION":
        return last['close'] > prev['close']
    elif sweep_type == "SWEEP_HIGH_REJECTION":
        return last['close'] < prev['close']
    
    return True


def refine_entry(candles: List[Dict], trend: str) -> float:
    if not candles:
        return 0
    last = candles[-1]
    if trend == "UPTREND":
        pullback = (last['high'] - last['low']) * 0.3
        return round(last['low'] + pullback, 2)
    elif trend == "DOWNTREND":
        pullback = (last['high'] - last['low']) * 0.3
        return round(last['high'] - pullback, 2)
    return last.get('close', 0)


def build_trade_levels(entry: float, trend: str) -> Dict:
    if trend == "UPTREND":
        return {
            "entry": entry,
            "sl": round(entry * (1 - SL_PERCENT), 2),
            "tp1": round(entry * (1 + TP1_PERCENT), 2),
            "tp2": round(entry * (1 + TP2_PERCENT), 2),
            "tp3": round(entry * (1 + TP3_PERCENT), 2)
        }
    else:
        return {
            "entry": entry,
            "sl": round(entry * (1 + SL_PERCENT), 2),
            "tp1": round(entry * (1 - TP1_PERCENT), 2),
            "tp2": round(entry * (1 - TP2_PERCENT), 2),
            "tp3": round(entry * (1 - TP3_PERCENT), 2)
        }


def process_pair(pair: str) -> Optional[Dict]:
    try:
        candles_1h = get_data(f"{pair}:1h")
        candles_4h_data = get_data(f"{pair}:4h")
        
        oi_raw = get_data(f"{pair}:oi")
        oi = float(oi_raw) if oi_raw and isinstance(oi_raw, (int, float)) else 0
        
        oi_history_raw = get_data(f"{pair}:oi_history")
        oi_history = oi_history_raw if isinstance(oi_history_raw, list) else []
    except Exception as e:
        logger.error(f"Data fetch error for {pair}: {e}")
        return None
    
    if not validate_candles(candles_1h):
        return None
    
    if not is_fresh(candles_1h):
        return None
    
    if not is_volatile(candles_1h):
        return None
    
    if not candles_4h_data:
        candles_4h = build_4h(candles_1h)
    else:
        candles_4h = candles_4h_data
    
    trend = detect_trend(candles_1h)
    htf_trend = detect_trend(candles_4h) if candles_4h else "RANGE"
    sweep = detect_sweep(candles_1h)
    volume = check_volume(oi, oi_history, candles_1h)
    strength = candle_strength(candles_1h[-1]) if candles_1h else 0
    
    htf_aligned = htf_trend == "RANGE" or htf_trend == trend
    is_reversal = detect_reversal(candles_1h, sweep)
    
    confidence = calculate_confidence(trend, sweep, volume, strength, htf_aligned, is_reversal)
    
    if confidence < MIN_CONFIDENCE:
        return None
    
    signal_type = "BUY" if trend == "UPTREND" else "SELL"
    entry = refine_entry(candles_1h, trend)
    levels = build_trade_levels(entry, trend)
    risk_pct = round(abs(entry - levels["sl"]) / entry * 100, 2)
    
    register_active_pair(pair)
    
    return {
        "pair": pair,
        "signal": signal_type,
        "confidence": confidence,
        "trend": f"{trend} ({htf_trend})",
        "liquidity": sweep,
        "volume": volume,
        "timestamp": datetime.utcnow().isoformat(),
        **levels,
        "risk_pct": risk_pct
    }


def scan_all_pairs(max_signals: int = 5) -> List[Dict]:
    all_signals = []
    debug_scores = []
    error_count = 0
    
    for pair in PAIRS:
        try:
            result = process_pair_debug(pair)
            
            if result is None:
                debug_scores.append((pair, {'score': 0, 'trend': 'NO_DATA', 'sweep': None, 'volume': False}))
                continue
            
            if not isinstance(result, tuple):
                logger.error(f"{pair}: process_pair_debug returned {type(result).__name__}: {result}")
                debug_scores.append((pair, {'score': 0, 'trend': 'FUNC_ERROR', 'sweep': None, 'volume': False}))
                error_count += 1
                continue
            
            signal, score_info = result
            
            if score_info:
                debug_scores.append((pair, score_info))
            else:
                debug_scores.append((pair, {'score': 0, 'trend': 'NO_INFO', 'sweep': None, 'volume': False}))
            
            if signal:
                all_signals.append(signal)
        except Exception as e:
            logger.error(f"Error processing {pair}: {e}")
            debug_scores.append((pair, {'score': 0, 'trend': 'EXCEPTION', 'sweep': None, 'volume': False}))
            error_count += 1
    
    if error_count > 0:
        logger.warning(f"⚠️ Errors this scan: {error_count}")
    
    debug_scores.sort(key=lambda x: x[1]['score'] if x[1] and isinstance(x[1], dict) else 0, reverse=True)
    
    logger.info(f"=== TOP 10 SCORES ===")
    for pair, info in debug_scores[:10]:
        if info and isinstance(info, dict):
            logger.info(f"{pair}: score={info.get('score', 0)}, trend={info.get('trend', '?')}, sweep={info.get('sweep')}, vol={info.get('volume')}")
        else:
            logger.info(f"{pair}: score=0, info={info}")
    
    all_signals = sorted(all_signals, key=lambda x: x['confidence'], reverse=True)
    
    valid_signals = [s for s in all_signals if is_new_signal(s)]
    
    return valid_signals[:max_signals]


def process_pair_debug(pair: str) -> tuple:
    candles_1h = get_data(f"{pair}:1h")
    candles_4h_data = get_data(f"{pair}:4h")
    oi = get_data(f"{pair}:oi") or 0
    oi_history = get_data(f"{pair}:oi_history") or []
    
    if not validate_candles(candles_1h):
        return None, None
    
    if not is_fresh(candles_1h):
        return None, {'score': 0, 'trend': 'NOT_FRESH', 'sweep': None, 'volume': False}
    
    if not is_volatile(candles_1h):
        return None, {'score': 0, 'trend': 'NOT_VOLATILE', 'sweep': None, 'volume': False}
    
    if not candles_4h_data:
        candles_4h = build_4h(candles_1h)
    else:
        candles_4h = candles_4h_data
    
    trend = detect_trend(candles_1h)
    htf_trend = detect_trend(candles_4h) if candles_4h else "RANGE"
    sweep = detect_sweep(candles_1h)
    volume = check_volume(oi, oi_history, candles_1h)
    strength = candle_strength(candles_1h[-1]) if candles_1h else 0
    
    htf_aligned = htf_trend == "RANGE" or htf_trend == trend
    is_rev = detect_reversal(candles_1h, sweep)
    
    confidence = calculate_confidence(trend, sweep, volume, strength, htf_aligned, is_rev)
    
    score_info = {
        'score': confidence,
        'trend': trend,
        'htf': htf_trend,
        'sweep': sweep,
        'volume': volume,
        'is_reversal': is_rev
    }
    
    if confidence < MIN_CONFIDENCE:
        return None, score_info
    
    signal_type = "BUY" if trend == "UPTREND" else "SELL"
    entry = refine_entry(candles_1h, trend)
    levels = build_trade_levels(entry, trend)
    risk_pct = round(abs(entry - levels["sl"]) / entry * 100, 2) if entry > 0 else 0
    
    register_active_pair(pair)
    
    return {
        "pair": pair,
        "signal": signal_type,
        "confidence": confidence,
        "trend": f"{trend} ({htf_trend})",
        "liquidity": sweep,
        "volume": volume,
        "timestamp": datetime.utcnow().isoformat(),
        **levels,
        "risk_pct": risk_pct
    }, score_info
