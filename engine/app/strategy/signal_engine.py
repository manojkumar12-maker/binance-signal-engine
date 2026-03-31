from typing import Dict, List, Optional
from datetime import datetime
from core.config import (
    PAIRS, SL_PERCENT, TP1_PERCENT, TP2_PERCENT, TP3_PERCENT, MIN_CONFIDENCE
)
from core.redis_client import get_data
from data.candle_builder import build_4h
import logging

logger = logging.getLogger(__name__)


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
    
    return oi_spike or absorption


def calculate_confidence(trend: str, sweep: Optional[str], volume: bool, strength: int = 0) -> int:
    score = 0
    if trend != "RANGE":
        score += 25
    if sweep:
        score += 25
    if volume:
        score += 30
    score += min(strength, 20)
    return min(score, 100)


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
    candles_1h = get_data(f"{pair}:1h")
    candles_4h_data = get_data(f"{pair}:4h")
    oi = get_data(f"{pair}:oi") or 0
    oi_history = get_data(f"{pair}:oi_history") or []
    
    if not candles_1h or len(candles_1h) < 20:
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
    
    if trend == "RANGE":
        return None
    
    if htf_trend != "RANGE" and htf_trend != trend:
        return None
    
    if not align_sweep(trend, sweep):
        return None
    
    confidence = calculate_confidence(trend, sweep, volume, strength)
    
    if confidence < MIN_CONFIDENCE:
        return None
    
    signal_type = "BUY" if trend == "UPTREND" else "SELL"
    entry = refine_entry(candles_1h, trend)
    levels = build_trade_levels(entry, trend)
    risk_pct = round(abs(entry - levels["sl"]) / entry * 100, 2)
    
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


def scan_all_pairs() -> List[Dict]:
    signals = []
    for pair in PAIRS:
        try:
            signal = process_pair(pair)
            if signal:
                signals.append(signal)
        except Exception as e:
            logger.error(f"Error processing {pair}: {e}")
    return signals
