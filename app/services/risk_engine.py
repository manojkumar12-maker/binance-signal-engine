from typing import Dict, Tuple
import config


def calculate_dynamic_sl(
    entry: float,
    candles: list,
    signal: str,
    atr_multiplier: float = 1.5
) -> Tuple[float, float]:
    if atr_multiplier is None:
        atr_multiplier = config.ATR_MULTIPLIER
    
    from app.services import volume
    atr = volume.calculate_atr(candles)
    sl_distance = atr * atr_multiplier
    
    min_sl_distance = entry * 0.003
    if sl_distance < min_sl_distance:
        sl_distance = min_sl_distance
    
    if signal == "BUY":
        sl = entry - sl_distance
    else:
        sl = entry + sl_distance
    
    risk_pct = round(abs(entry - sl) / entry * 100, 2)
    
    return sl, risk_pct


def calculate_dynamic_tp(
    entry: float,
    signal: str,
    confidence: float,
    atr: float = 0.0
) -> Tuple[float, float, float]:
    if confidence >= 90:
        tp1_mult = config.TP1_PERCENT * 1.2
        tp2_mult = config.TP2_PERCENT * 1.2
        tp3_mult = config.TP3_PERCENT * 1.2
    elif confidence >= 80:
        tp1_mult = config.TP1_PERCENT
        tp2_mult = config.TP2_PERCENT
        tp3_mult = config.TP3_PERCENT
    else:
        tp1_mult = config.TP1_PERCENT * 0.8
        tp2_mult = config.TP2_PERCENT * 0.8
        tp3_mult = config.TP3_PERCENT * 0.8
    
    if signal == "BUY":
        tp1 = entry * (1 + tp1_mult)
        tp2 = entry * (1 + tp2_mult)
        tp3 = entry * (1 + tp3_mult)
    else:
        tp1 = entry * (1 - tp1_mult)
        tp2 = entry * (1 - tp2_mult)
        tp3 = entry * (1 - tp3_mult)
    
    return tp1, tp2, tp3


def calculate_position_size(
    account_balance: float,
    risk_percent: float,
    entry: float,
    sl: float
) -> float:
    if entry <= 0 or sl <= 0:
        return 0
    
    risk_amount = account_balance * risk_percent
    stop_distance = abs(entry - sl)
    
    if stop_distance == 0:
        return 0
    
    position_size = risk_amount / stop_distance
    return round(position_size, 3)


def get_dynamic_risk(confidence: float) -> float:
    if confidence >= config.SNIPER_MODE_CONFIDENCE:
        return config.HIGH_CONFIDENCE_RISK
    elif confidence >= 70:
        return config.RISK_PER_TRADE
    else:
        return config.LOW_CONFIDENCE_RISK


def calculate_rr_ratio(entry: float, sl: float, tp: float, signal: str) -> float:
    if entry <= 0 or sl <= 0 or tp <= 0:
        return 0
    
    if signal == "BUY":
        risk = entry - sl
        reward = tp - entry
    else:
        risk = sl - entry
        reward = entry - tp
    
    if risk == 0:
        return 0
    
    return reward / risk


def validate_rr_ratio(entry: float, sl: float, tp1: float, signal: str) -> Tuple[bool, float]:
    rr = calculate_rr_ratio(entry, sl, tp1, signal)
    
    is_valid = rr >= config.MIN_RR_RATIO
    
    return is_valid, round(rr, 2)


def calculate_risk_metrics(
    entry: float,
    sl: float,
    tp1: float,
    tp2: float,
    tp3: float,
    signal: str,
    confidence: float,
    account_balance: float = 10000
) -> Dict:
    rr1 = calculate_rr_ratio(entry, sl, tp1, signal)
    rr2 = calculate_rr_ratio(entry, sl, tp2, signal)
    rr3 = calculate_rr_ratio(entry, sl, tp3, signal)
    
    risk_pct = round(abs(entry - sl) / entry * 100, 2)
    risk_amount = account_balance * get_dynamic_risk(confidence)
    
    position_size = calculate_position_size(
        account_balance,
        get_dynamic_risk(confidence),
        entry,
        sl
    )
    
    return {
        "risk_pct": risk_pct,
        "risk_amount": round(risk_amount, 2),
        "position_size": position_size,
        "rr_tp1": round(rr1, 2),
        "rr_tp2": round(rr2, 2),
        "rr_tp3": round(rr3, 2),
        "valid_rr": rr1 >= config.MIN_RR_RATIO,
        "dynamic_risk": get_dynamic_risk(confidence)
    }


def adjust_sl_for_structure(candles: list, sl: float, signal: str) -> float:
    if not candles or len(candles) < 20:
        return sl
    
    recent_lows = [c['low'] for c in candles[-20:]]
    recent_highs = [c['high'] for c in candles[-20:]]
    
    if signal == "BUY":
        nearest_support = max([l for l in recent_lows if l < sl]) if any(l < sl for l in recent_lows) else sl
        
        if nearest_support < sl and (sl - nearest_support) / sl < 0.02:
            return nearest_support * 0.998
    else:
        nearest_resistance = min([h for h in recent_highs if h > sl]) if any(h > sl for h in recent_highs) else sl
        
        if nearest_resistance > sl and (nearest_resistance - sl) / sl < 0.02:
            return nearest_resistance * 1.002
    
    return sl
