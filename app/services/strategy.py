import logging
import config
from app.services import market
from app.services import bias_engine

logger = logging.getLogger(__name__)

def generate_signal(pair: str, timeframe: str = "1h", fetch_oi: bool = True, use_bias: bool = True) -> dict:
    candles = market.get_klines(pair, timeframe, config.CANDLE_LIMIT)
    
    if not candles or len(candles) < 20:
        return {
            "pair": pair,
            "signal": "NO TRADE",
            "entry": 0,
            "sl": 0,
            "tp1": 0,
            "tp2": 0,
            "tp3": 0,
            "confidence": 0,
            "reason": "Insufficient data"
        }
    
    parsed_candles = market.parse_klines(candles)
    return generate_signal_from_candles(pair, parsed_candles)

def generate_signal_from_candles(pair: str, candles: list) -> dict:
    if not candles or len(candles) < 20:
        return {
            "pair": pair,
            "signal": "NO TRADE",
            "entry": 0,
            "sl": 0,
            "tp1": 0,
            "tp2": 0,
            "tp3": 0,
            "confidence": 0,
            "reason": "Insufficient candles"
        }
    
    current_price = candles[-1]["close"]
    current_volume = candles[-1]["volume"]
    
    trend = bias_engine.calculate_trend(candles)
    
    swing_high = max([c["high"] for c in candles[-10:]])
    swing_low = min([c["low"] for c in candles[-10:])
    
    liquidity = detect_liquidity_sweep(candles, swing_high, swing_low)
    
    volume_confirmed = check_volume_confirm(candles)
    
    signal = "NO TRADE"
    confidence = 0
    reasons = []
    
    if trend == "UPTREND":
        signal = "BUY"
        confidence += 30
        reasons.append("Uptrend")
    elif trend == "DOWNTREND":
        signal = "SELL"
        confidence += 30
        reasons.append("Downtrend")
    else:
        reasons.append("No clear trend")
    
    if liquidity:
        confidence += 30
        reasons.append(f"Liquidity: {liquidity}")
    
    if volume_confirmed:
        confidence += 40
        reasons.append("Volume confirmed")
    
    if confidence < config.MIN_CONFIDENCE:
        return {
            "pair": pair,
            "signal": "NO TRADE",
            "entry_primary": current_price,
            "sl": 0,
            "tp1": 0,
            "tp2": 0,
            "tp3": 0,
            "confidence": confidence,
            "trend": trend,
            "liquidity": liquidity,
            "volume": volume_confirmed,
            "reason": "; ".join(reasons)
        }
    
    entry = current_price
    risk_pct = config.SL_PERCENT * 100
    
    if signal == "BUY":
        sl = entry * (1 - config.SL_PERCENT)
        tp1 = entry * (1 + config.TP1_PERCENT)
        tp2 = entry * (1 + config.TP2_PERCENT)
        tp3 = entry * (1 + config.TP3_PERCENT)
    else:
        sl = entry * (1 + config.SL_PERCENT)
        tp1 = entry * (1 - config.TP1_PERCENT)
        tp2 = entry * (1 - config.TP2_PERCENT)
        tp3 = entry * (1 - config.TP3_PERCENT)
    
    sl = config.format_price(pair, sl)
    tp1 = config.format_price(pair, tp1)
    tp2 = config.format_price(pair, tp2)
    tp3 = config.format_price(pair, tp3)
    
    return {
        "pair": pair,
        "signal": signal,
        "entry_primary": entry,
        "entry_limit": entry,
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "confidence": confidence,
        "risk_pct": round(risk_pct, 2),
        "trend": trend,
        "liquidity": liquidity,
        "volume": volume_confirmed,
        "regime": "NORMAL"
    }

def detect_liquidity_sweep(candles: list, swing_high: float, swing_low: float) -> str:
    recent = candles[-5:]
    
    for c in recent:
        if c["high"] >= swing_high * 0.999 and c["close"] < c["high"] * 0.998:
            return "SWEEP_HIGH_REJECTION"
        if c["low"] <= swing_low * 1.001 and c["close"] > c["low"] * 1.002:
            return "SWEEP_LOW_REJECTION"
    
    return None

def check_volume_confirm(candles: list) -> bool:
    if len(candles) < 20:
        return False
    
    recent_volumes = [c["volume"] for c in candles[-20:-1]]
    avg_volume = sum(recent_volumes) / len(recent_volumes)
    current_volume = candles[-1]["volume"]
    
    return current_volume > avg_volume * 1.2