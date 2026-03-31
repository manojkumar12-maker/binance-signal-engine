from typing import Dict, Optional
from datetime import datetime
import config
from app.services import market, structure, liquidity, volume, scoring


def generate_signal(pair: str, timeframe: str = "1h") -> Dict:
    try:
        candles = market.get_klines(pair, timeframe, config.CANDLE_LIMIT)
    except Exception as e:
        return {
            "pair": pair,
            "signal": "NO TRADE",
            "entry": 0,
            "sl": 0,
            "tp1": 0,
            "tp2": 0,
            "tp3": 0,
            "confidence": 0,
            "trend": "UNKNOWN",
            "liquidity": None,
            "volume": False,
            "timestamp": datetime.utcnow().isoformat(),
            "reason": f"Error fetching data: {str(e)}"
        }
    
    if not candles:
        return {
            "pair": pair,
            "signal": "NO TRADE",
            "entry": 0,
            "sl": 0,
            "tp1": 0,
            "tp2": 0,
            "tp3": 0,
            "confidence": 0,
            "trend": "UNKNOWN",
            "liquidity": None,
            "volume": False,
            "timestamp": datetime.utcnow().isoformat(),
            "reason": "Unable to fetch market data"
        }
    
    try:
        current_price = candles[-1]["close"]
        oi_data = market.get_open_interest(pair)
        
        trend = structure.detect_trend(candles)
        sweep = liquidity.detect_sweep(candles)
        volume_confirmed = volume.check_volume_confirmation(oi_data)
        
        if trend == "RANGE":
            return {
                "pair": pair,
                "signal": "NO TRADE",
                "entry": current_price,
                "sl": 0,
                "tp1": 0,
                "tp2": 0,
                "tp3": 0,
                "confidence": 0,
                "trend": trend,
                "liquidity": sweep,
                "volume": volume_confirmed,
                "timestamp": datetime.utcnow().isoformat(),
                "reason": "Market in Range - No clear trend"
            }
        
        if sweep is None:
            return {
                "pair": pair,
                "signal": "NO TRADE",
                "entry": current_price,
                "sl": 0,
                "tp1": 0,
                "tp2": 0,
                "tp3": 0,
                "confidence": 0,
                "trend": trend,
                "liquidity": None,
                "volume": volume_confirmed,
                "timestamp": datetime.utcnow().isoformat(),
                "reason": "No liquidity sweep detected"
            }
        
        confidence = scoring.calculate_confidence(trend, sweep, volume_confirmed)
        
        signal_type = "BUY" if trend == "UPTREND" else "SELL"
        
        if signal_type == "BUY":
            entry = current_price
            sl = current_price * (1 - config.SL_PERCENT)
            tp1 = current_price * (1 + config.TP1_PERCENT)
            tp2 = current_price * (1 + config.TP2_PERCENT)
            tp3 = current_price * (1 + config.TP3_PERCENT)
        else:
            entry = current_price
            sl = current_price * (1 + config.SL_PERCENT)
            tp1 = current_price * (1 - config.TP1_PERCENT)
            tp2 = current_price * (1 - config.TP2_PERCENT)
            tp3 = current_price * (1 - config.TP3_PERCENT)
        
        return {
            "pair": pair,
            "signal": signal_type,
            "entry": round(entry, 2),
            "sl": round(sl, 2),
            "tp1": round(tp1, 2),
            "tp2": round(tp2, 2),
            "tp3": round(tp3, 2),
            "confidence": confidence,
            "trend": trend,
            "liquidity": sweep,
            "volume": volume_confirmed,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        return {
            "pair": pair,
            "signal": "NO TRADE",
            "entry": 0,
            "sl": 0,
            "tp1": 0,
            "tp2": 0,
            "tp3": 0,
            "confidence": 0,
            "trend": "ERROR",
            "liquidity": None,
            "volume": False,
            "timestamp": datetime.utcnow().isoformat(),
            "reason": f"Processing error: {str(e)}"
        }
