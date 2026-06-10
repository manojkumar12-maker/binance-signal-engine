from typing import Dict, List, Optional
import logging
from datetime import datetime

logger = logging.getLogger("trade_manager")


def calculate_position_size(balance: float, risk_pct: float, entry: float, sl: float) -> float:
    if entry <= 0 or sl <= 0 or entry == sl:
        return 0
    
    risk_amount = balance * (risk_pct / 100)
    stop_distance = abs(entry - sl)
    
    if stop_distance == 0:
        return 0
    
    position_size = risk_amount / stop_distance
    return position_size


def validate_trade_quality(signal: Dict) -> tuple[bool, Optional[str]]:
    if not signal:
        return False, "No signal"
    
    confidence = signal.get("confidence", 0)
    if confidence < 70:
        return False, f"Low confidence: {confidence}"
    
    risk_pct = signal.get("risk_pct", 0)
    if risk_pct <= 0 or risk_pct > 2.5:
        return False, f"Invalid risk: {risk_pct}%"
    
    entry = signal.get("entry_primary", 0)
    sl = signal.get("sl", 0)
    if entry <= 0 or sl <= 0:
        return False, "Invalid entry/sl"
    
    regime = signal.get("regime", "TRANSITION")
    if regime in ["LOW_VOL", "RANGE"]:
        return False, f"Bad regime: {regime}"
    
    market_bias = signal.get("market_bias", "NEUTRAL")
    signal_direction = signal.get("signal", "")
    
    if market_bias == "BEARISH" and signal_direction == "BUY":
        return False, "Trading against bias"
    if market_bias == "BULLISH" and signal_direction == "SELL":
        return False, "Trading against bias"
    
    return True, None


def get_optimal_entry(signal: Dict, current_price: float) -> Dict:
    signal_type = signal.get("signal", "")
    entry_primary = signal.get("entry_primary", current_price)
    entry_limit = signal.get("entry_limit", entry_primary)
    
    if signal_type == "BUY":
        if current_price <= entry_limit:
            return {
                "type": "LIMIT",
                "entry": entry_limit,
                "reason": "Price at pullback level"
            }
        else:
            return {
                "type": "MARKET",
                "entry": current_price,
                "reason": "Price moved past limit, take market"
            }
    else:
        if current_price >= entry_limit:
            return {
                "type": "LIMIT",
                "entry": entry_limit,
                "reason": "Price at pullback level"
            }
        else:
            return {
                "type": "MARKET",
                "entry": current_price,
                "reason": "Price moved past limit, take market"
            }


def calculate_tp_levels(entry: float, sl: float, signal_type: str) -> Dict:
    risk = abs(entry - sl)
    
    tp1 = entry + (risk * 1) if signal_type == "BUY" else entry - (risk * 1)
    tp2 = entry + (risk * 2) if signal_type == "BUY" else entry - (risk * 2)
    tp3 = entry + (risk * 3) if signal_type == "BUY" else entry - (risk * 3)
    
    return {
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "breakeven": entry
    }


def should_trail_stop(current_price: float, tp_hit: str, trail_level: float, signal_type: str) -> float:
    if tp_hit == "TP1":
        return trail_level
    elif tp_hit == "TP2":
        if signal_type == "BUY":
            return max(trail_level, current_price - (current_price * 0.002))
        else:
            return max(trail_level, current_price + (current_price * 0.002))
    return trail_level
