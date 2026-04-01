from typing import Dict, Optional, Tuple
from datetime import datetime
import config
from app.services import market, structure, liquidity, volume, scoring, bias_engine


def calculate_atr(candles: list, period: int = 14) -> float:
    return volume.calculate_atr(candles, period)


def calculate_atr_based_sl(entry: float, candles: list, signal_type: str) -> Tuple[float, float]:
    atr = calculate_atr(candles)
    sl_distance = atr * config.ATR_MULTIPLIER
    
    if signal_type == "BUY":
        sl = entry - sl_distance
    else:
        sl = entry + sl_distance
    
    return round(sl, 2), round(sl_distance / entry * 100, 2)


def refine_entry(candles: list, trend: str) -> Tuple[float, float]:
    last = candles[-1]
    current_price = last['close']
    
    if trend == "UPTREND":
        pullback = (last['high'] - last['low']) * 0.3
        entry_limit = round(last['low'] + pullback, 2)
    elif trend == "DOWNTREND":
        pullback = (last['high'] - last['low']) * 0.3
        entry_limit = round(last['high'] - pullback, 2)
    else:
        entry_limit = current_price
    
    return round(current_price, 2), entry_limit


def check_volatility_filter(candles: list, current_price: float) -> Tuple[bool, float]:
    atr_ratio = volume.get_atr_ratio(candles, current_price)
    
    if atr_ratio < config.MIN_ATR_RATIO:
        return False, round(atr_ratio, 6)
    
    return True, round(atr_ratio, 6)


def generate_signal(pair: str, timeframe: str = "1h", fetch_oi: bool = True, use_bias: bool = True) -> Dict:
    try:
        candles = market.get_klines(pair, timeframe, config.CANDLE_LIMIT)
        htf_candles = market.get_klines(pair, "4h", config.CANDLE_LIMIT)
    except Exception as e:
        return {
            "pair": pair,
            "signal": "NO TRADE",
            "entry_primary": 0, "entry_limit": 0,
            "sl": 0, "tp1": 0, "tp2": 0, "tp3": 0,
            "confidence": 0,
            "trend": "UNKNOWN",
            "liquidity": None,
            "volume": False,
            "atr_ratio": 0,
            "timestamp": datetime.utcnow().isoformat(),
            "reason": f"Error fetching data: {str(e)}"
        }
    
    if not candles or len(candles) < 20:
        return {
            "pair": pair,
            "signal": "NO TRADE",
            "entry_primary": 0, "entry_limit": 0,
            "sl": 0, "tp1": 0, "tp2": 0, "tp3": 0,
            "confidence": 0,
            "trend": "UNKNOWN",
            "liquidity": None,
            "volume": False,
            "atr_ratio": 0,
            "timestamp": datetime.utcnow().isoformat(),
            "reason": "Insufficient market data"
        }
    
    try:
        current_price = candles[-1]["close"]
        oi_data = [] if not fetch_oi else market.get_open_interest(pair)
        
        trend = structure.detect_trend(candles)
        htf_trend = structure.detect_htf_trend(htf_candles) if htf_candles else "RANGE"
        sweep = liquidity.detect_sweep(candles)
        volume_result = volume.check_volume_confirmation(oi_data, candles)
        
        if isinstance(volume_result, tuple):
            volume_confirmed, volume_spike = volume_result
        else:
            volume_confirmed = volume_result
            volume_spike = False
        
        strength = structure.candle_strength(candles[-1])
        volume_strength = volume.get_volume_strength(oi_data)
        total_strength = strength + volume_strength
        
        volatility_pass, atr_ratio = check_volatility_filter(candles, current_price)
        
        if not volatility_pass:
            return {
                "pair": pair,
                "signal": "NO TRADE",
                "entry_primary": round(current_price, 2),
                "entry_limit": 0,
                "sl": 0, "tp1": 0, "tp2": 0, "tp3": 0,
                "confidence": 0,
                "trend": f"{trend} ({htf_trend})",
                "liquidity": sweep,
                "volume": volume_confirmed,
                "atr_ratio": atr_ratio,
                "timestamp": datetime.utcnow().isoformat(),
                "reason": f"Low volatility (ATR ratio: {atr_ratio})"
            }
        
        if trend == "RANGE":
            return {
                "pair": pair,
                "signal": "NO TRADE",
                "entry_primary": round(current_price, 2),
                "entry_limit": 0,
                "sl": 0, "tp1": 0, "tp2": 0, "tp3": 0,
                "confidence": 0,
                "trend": f"{trend} ({htf_trend})",
                "liquidity": sweep,
                "volume": volume_confirmed,
                "atr_ratio": atr_ratio,
                "timestamp": datetime.utcnow().isoformat(),
                "reason": "Market in Range"
            }
        
        htf_aligned = htf_trend == "RANGE" or htf_trend == trend
        
        if not htf_aligned:
            confidence = scoring.calculate_confidence(trend, sweep, volume_confirmed, total_strength, volume_spike)
            if confidence < config.MIN_CONFIDENCE:
                return {
                    "pair": pair,
                    "signal": "NO TRADE",
                    "entry_primary": round(current_price, 2),
                    "entry_limit": 0,
                    "sl": 0, "tp1": 0, "tp2": 0, "tp3": 0,
                    "confidence": confidence,
                    "trend": f"{trend} ({htf_trend})",
                    "liquidity": sweep,
                    "volume": volume_confirmed,
                    "atr_ratio": atr_ratio,
                    "timestamp": datetime.utcnow().isoformat(),
                    "reason": f"HTF/LTF trend mismatch (confidence: {confidence})"
                }
        
        liquidity_aligned = liquidity.align_sweep_with_trend(trend, sweep)
        
        if not liquidity_aligned:
            confidence = scoring.calculate_confidence(trend, sweep, volume_confirmed, total_strength, volume_spike)
            if confidence < config.MIN_CONFIDENCE:
                return {
                    "pair": pair,
                    "signal": "NO TRADE",
                    "entry_primary": round(current_price, 2),
                    "entry_limit": 0,
                    "sl": 0, "tp1": 0, "tp2": 0, "tp3": 0,
                    "confidence": confidence,
                    "trend": f"{trend} ({htf_trend})",
                    "liquidity": sweep,
                    "volume": volume_confirmed,
                    "atr_ratio": atr_ratio,
                    "timestamp": datetime.utcnow().isoformat(),
                    "reason": f"Sweep not aligned with trend (confidence: {confidence})"
                }
        
        confidence = scoring.calculate_confidence(trend, sweep, volume_confirmed, total_strength, volume_spike)
        
        market_bias = None
        
        if use_bias and pair != "BTCUSDT":
            try:
                btc_1h = market.get_klines("BTCUSDT", "1h", config.CANDLE_LIMIT)
                btc_4h = market.get_klines("BTCUSDT", "4h", config.CANDLE_LIMIT)
                market_bias = bias_engine.get_market_bias(btc_1h, btc_4h)
                
                signal_for_check = "BUY" if trend == "UPTREND" else "SELL"
                bias_passed, bias_reason = bias_engine.apply_bias_filter(signal_for_check, market_bias)
                
                if not bias_passed:
                    return {
                        "pair": pair,
                        "signal": "NO TRADE",
                        "entry_primary": round(current_price, 2),
                        "entry_limit": 0,
                        "sl": 0, "tp1": 0, "tp2": 0, "tp3": 0,
                        "confidence": confidence,
                        "trend": f"{trend} ({htf_trend})",
                        "liquidity": sweep,
                        "volume": volume_confirmed,
                        "atr_ratio": atr_ratio,
                        "market_bias": market_bias,
                        "timestamp": datetime.utcnow().isoformat(),
                        "reason": f"Market bias: {bias_reason}"
                    }
                
                confidence = bias_engine.apply_bias_boost(confidence, signal_for_check, market_bias)
            except Exception:
                pass
        
        if confidence < config.MIN_CONFIDENCE:
            return {
                "pair": pair,
                "signal": "NO TRADE",
                "entry_primary": round(current_price, 2),
                "entry_limit": 0,
                "sl": 0, "tp1": 0, "tp2": 0, "tp3": 0,
                "confidence": confidence,
                "trend": f"{trend} ({htf_trend})",
                "liquidity": sweep,
                "volume": volume_confirmed,
                "atr_ratio": atr_ratio,
                "timestamp": datetime.utcnow().isoformat(),
                "reason": f"Below minimum confidence threshold ({config.MIN_CONFIDENCE})"
            }
        
        signal_type = "BUY" if trend == "UPTREND" else "SELL"
        
        entry_primary, entry_limit = refine_entry(candles, trend)
        
        sl, risk_pct = calculate_atr_based_sl(entry_primary, candles, signal_type)
        
        if signal_type == "BUY":
            tp1 = entry_primary * (1 + config.TP1_PERCENT)
            tp2 = entry_primary * (1 + config.TP2_PERCENT)
            tp3 = entry_primary * (1 + config.TP3_PERCENT)
        else:
            tp1 = entry_primary * (1 - config.TP1_PERCENT)
            tp2 = entry_primary * (1 - config.TP2_PERCENT)
            tp3 = entry_primary * (1 - config.TP3_PERCENT)
        
        return {
            "pair": pair,
            "signal": signal_type,
            "entry_primary": entry_primary,
            "entry_limit": entry_limit,
            "sl": sl,
            "tp1": round(tp1, 2),
            "tp2": round(tp2, 2),
            "tp3": round(tp3, 2),
            "confidence": confidence,
            "trend": f"{trend} ({htf_trend})",
            "liquidity": sweep,
            "volume": volume_confirmed,
            "atr_ratio": atr_ratio,
            "risk_pct": risk_pct,
            "market_bias": market_bias,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        return {
            "pair": pair,
            "signal": "NO TRADE",
            "entry_primary": 0, "entry_limit": 0,
            "sl": 0, "tp1": 0, "tp2": 0, "tp3": 0,
            "confidence": 0,
            "trend": "ERROR",
            "liquidity": None,
            "volume": False,
            "atr_ratio": 0,
            "market_bias": None,
            "timestamp": datetime.utcnow().isoformat(),
            "reason": f"Processing error: {str(e)}"
        }