from typing import Dict, Optional
from datetime import datetime
import config
from app.services import market, structure, liquidity, volume, scoring


def refine_entry(candles: list, trend: str) -> float:
    last = candles[-1]
    prev = candles[-2]
    
    if trend == "UPTREND":
        pullback = (last['high'] - last['low']) * 0.3
        return round(last['low'] + pullback, 2)
    
    elif trend == "DOWNTREND":
        pullback = (last['high'] - last['low']) * 0.3
        return round(last['high'] - pullback, 2)
    
    return last['close']


def generate_signal(pair: str, timeframe: str = "1h") -> Dict:
    try:
        candles = market.get_klines(pair, timeframe, config.CANDLE_LIMIT)
        htf_candles = market.get_klines(pair, "4h", config.CANDLE_LIMIT)
    except Exception as e:
        return {
            "pair": pair,
            "signal": "NO TRADE",
            "entry": 0, "sl": 0, "tp1": 0, "tp2": 0, "tp3": 0,
            "confidence": 0,
            "trend": "UNKNOWN",
            "liquidity": None,
            "volume": False,
            "timestamp": datetime.utcnow().isoformat(),
            "reason": f"Error fetching data: {str(e)}"
        }
    
    if not candles or len(candles) < 20:
        return {
            "pair": pair,
            "signal": "NO TRADE",
            "entry": 0, "sl": 0, "tp1": 0, "tp2": 0, "tp3": 0,
            "confidence": 0,
            "trend": "UNKNOWN",
            "liquidity": None,
            "volume": False,
            "timestamp": datetime.utcnow().isoformat(),
            "reason": "Insufficient market data"
        }
    
    try:
        current_price = candles[-1]["close"]
        oi_data = market.get_open_interest(pair)
        
        trend = structure.detect_trend(candles)
        htf_trend = structure.detect_htf_trend(htf_candles) if htf_candles else "RANGE"
        sweep = liquidity.detect_sweep(candles)
        volume_confirmed = volume.check_volume_confirmation(oi_data, candles)
        
        strength = structure.candle_strength(candles[-1])
        volume_strength = volume.get_volume_strength(oi_data)
        total_strength = strength + volume_strength
        
        if trend == "RANGE":
            return {
                "pair": pair,
                "signal": "NO TRADE",
                "entry": current_price, "sl": 0, "tp1": 0, "tp2": 0, "tp3": 0,
                "confidence": 0,
                "trend": f"{trend} ({htf_trend})",
                "liquidity": sweep,
                "volume": volume_confirmed,
                "timestamp": datetime.utcnow().isoformat(),
                "reason": "Market in Range"
            }
        
        if htf_trend != "RANGE" and htf_trend != trend:
            return {
                "pair": pair,
                "signal": "NO TRADE",
                "entry": current_price, "sl": 0, "tp1": 0, "tp2": 0, "tp3": 0,
                "confidence": 0,
                "trend": f"{trend} ({htf_trend})",
                "liquidity": sweep,
                "volume": volume_confirmed,
                "timestamp": datetime.utcnow().isoformat(),
                "reason": "HTF/LTF trend mismatch"
            }
        
        if not liquidity.align_sweep_with_trend(trend, sweep):
            return {
                "pair": pair,
                "signal": "NO TRADE",
                "entry": current_price, "sl": 0, "tp1": 0, "tp2": 0, "tp3": 0,
                "confidence": 0,
                "trend": f"{trend} ({htf_trend})",
                "liquidity": sweep,
                "volume": volume_confirmed,
                "timestamp": datetime.utcnow().isoformat(),
                "reason": "Sweep not aligned with trend"
            }
        
        confidence = scoring.calculate_confidence(trend, sweep, volume_confirmed, total_strength)
        
        signal_type = "BUY" if trend == "UPTREND" else "SELL"
        
        entry = refine_entry(candles, trend)
        
        if signal_type == "BUY":
            sl = entry * (1 - config.SL_PERCENT)
            tp1 = entry * (1 + config.TP1_PERCENT)
            tp2 = entry * (1 + config.TP2_PERCENT)
            tp3 = entry * (1 + config.TP3_PERCENT)
        else:
            sl = entry * (1 + config.SL_PERCENT)
            tp1 = entry * (1 - config.TP1_PERCENT)
            tp2 = entry * (1 - config.TP2_PERCENT)
            tp3 = entry * (1 - config.TP3_PERCENT)
        
        risk_pct = round((entry - sl) / entry * 100, 2) if entry > 0 else 0
        
        return {
            "pair": pair,
            "signal": signal_type,
            "entry": round(entry, 2),
            "sl": round(sl, 2),
            "tp1": round(tp1, 2),
            "tp2": round(tp2, 2),
            "tp3": round(tp3, 2),
            "confidence": confidence,
            "trend": f"{trend} ({htf_trend})",
            "liquidity": sweep,
            "volume": volume_confirmed,
            "risk_pct": risk_pct,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        return {
            "pair": pair,
            "signal": "NO TRADE",
            "entry": 0, "sl": 0, "tp1": 0, "tp2": 0, "tp3": 0,
            "confidence": 0,
            "trend": "ERROR",
            "liquidity": None,
            "volume": False,
            "timestamp": datetime.utcnow().isoformat(),
            "reason": f"Processing error: {str(e)}"
        }
