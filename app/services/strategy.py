from typing import Dict, Optional, Tuple
from datetime import datetime
import config
from app.services import market, structure, liquidity, volume, scoring, bias_engine


def calculate_atr(candles: list, period: int = 14) -> float:
    return volume.calculate_atr(candles, period)


def calculate_atr_based_sl(entry: float, candles: list, signal_type: str, pair: str = "BTCUSDT") -> Tuple[float, float]:
    atr = calculate_atr(candles)
    sl_distance = atr * config.ATR_MULTIPLIER
    
    if signal_type == "BUY":
        sl = entry - sl_distance
    else:
        sl = entry + sl_distance
    
    risk_pct = round(abs(entry - sl) / entry * 100, 2)
    
    return sl, risk_pct


def refine_entry(candles: list, trend: str, pair: str = "BTCUSDT") -> Tuple[float, float]:
    last = candles[-1]
    current_price = last['close']
    
    if trend == "UPTREND":
        pullback = (last['high'] - last['low']) * 0.3
        entry_limit = last['low'] + pullback
    elif trend == "DOWNTREND":
        pullback = (last['high'] - last['low']) * 0.3
        entry_limit = last['high'] - pullback
    else:
        entry_limit = current_price
    
    return current_price, entry_limit


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
        
        htf_aligned = htf_trend == "RANGE" or htf_trend == trend
        
        is_reversal = scoring.detect_reversal(candles, sweep)
        
        fake_breakout = scoring.detect_fake_breakout(candles)
        market_mode = scoring.get_market_mode(atr_ratio)
        
        liquidity_aligned = scoring.validate_liquidity(trend, sweep)
        
        if total_strength < 5:
            return {
                "pair": pair,
                "signal": "NO TRADE",
                "entry_primary": 0, "entry_limit": 0,
                "sl": 0, "tp1": 0, "tp2": 0, "tp3": 0,
                "confidence": 0,
                "trend": f"{trend} ({htf_trend})",
                "liquidity": sweep,
                "volume": volume_confirmed,
                "atr_ratio": atr_ratio,
                "timestamp": datetime.utcnow().isoformat(),
                "reason": "Weak candle strength"
            }
        
        confidence = scoring.calculate_confidence(
            trend, sweep, volume_confirmed, total_strength, volume_spike,
            htf_aligned=htf_aligned,
            market_bias=None,
            is_reversal=is_reversal
        )
        
        confidence = scoring.apply_fake_breakout_bonus(confidence, fake_breakout, "BUY" if trend == "UPTREND" else "SELL")
        confidence = scoring.apply_adaptive_scoring(confidence, market_mode, sweep, "BUY" if trend == "UPTREND" else "SELL")
        
        if not liquidity_aligned:
            confidence = max(0, confidence - 20)
        else:
            confidence += 5
        
        if not volatility_pass:
            confidence -= 10
        elif atr_ratio > 0.01:
            confidence += 5
        
        if trend == "RANGE" and not is_reversal:
            confidence = max(0, confidence - 25)
        
        if trend == "RANGE" and is_reversal:
            confidence += 10
        
        confidence = max(0, min(confidence, 100))
        
        market_bias = None
        
        signal_type = "BUY" if trend == "UPTREND" else "SELL"
        
        entry_primary, entry_limit = refine_entry(candles, trend, pair)
        
        sl, risk_pct = calculate_atr_based_sl(entry_primary, candles, signal_type, pair)
        
        if not config.validate_trade(entry_primary, sl):
            return {
                "pair": pair,
                "signal": "NO TRADE",
                "entry_primary": entry_primary,
                "entry_limit": entry_limit,
                "sl": sl,
                "tp1": 0, "tp2": 0, "tp3": 0,
                "confidence": confidence,
                "trend": f"{trend} ({htf_trend})",
                "liquidity": sweep,
                "volume": volume_confirmed,
                "atr_ratio": atr_ratio,
                "risk_pct": risk_pct,
                "market_bias": market_bias,
                "is_reversal": is_reversal,
                "market_mode": market_mode,
                "fake_breakout": fake_breakout,
                "timestamp": datetime.utcnow().isoformat(),
                "reason": "Invalid trade parameters"
            }
        
        if signal_type == "BUY":
            tp1 = entry_primary * (1 + config.TP1_PERCENT)
            tp2 = entry_primary * (1 + config.TP2_PERCENT)
            tp3 = entry_primary * (1 + config.TP3_PERCENT)
        else:
            tp1 = entry_primary * (1 - config.TP1_PERCENT)
            tp2 = entry_primary * (1 - config.TP2_PERCENT)
            tp3 = entry_primary * (1 - config.TP3_PERCENT)
        
        entry_primary = config.round_to_tick(pair, entry_primary)
        entry_limit = config.round_to_tick(pair, entry_limit)
        sl = config.round_to_tick(pair, sl)
        tp1 = config.round_to_tick(pair, tp1)
        tp2 = config.round_to_tick(pair, tp2)
        tp3 = config.round_to_tick(pair, tp3)
        
        return {
            "pair": pair,
            "signal": signal_type,
            "entry_primary": entry_primary,
            "entry_limit": entry_limit,
            "sl": sl,
            "tp1": tp1,
            "tp2": tp2,
            "tp3": tp3,
            "confidence": confidence,
            "trend": f"{trend} ({htf_trend})",
            "liquidity": sweep,
            "volume": volume_confirmed,
            "atr_ratio": atr_ratio,
            "risk_pct": risk_pct,
            "market_bias": market_bias,
            "is_reversal": is_reversal,
            "market_mode": market_mode,
            "fake_breakout": fake_breakout,
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
            "is_reversal": False,
            "timestamp": datetime.utcnow().isoformat(),
            "reason": f"Processing error: {str(e)}"
        }


def generate_signal_from_candles(pair: str, candles: list) -> Dict:
    """Generate signal from pre-fetched candles (for async scanner)"""
    try:
        if not candles or len(candles) < 20:
            return {
                "pair": pair,
                "signal": "NO TRADE",
                "confidence": 0,
                "reason": "Insufficient data"
            }
        
        current_price = candles[-1]["close"]
        
        trend = structure.detect_trend(candles)
        sweep = liquidity.detect_sweep(candles)
        
        volatility_pass, atr_ratio = check_volatility_filter(candles, current_price)
        
        strength = structure.candle_strength(candles[-1])
        total_strength = strength
        
        liquidity_aligned = scoring.validate_liquidity(trend, sweep)
        
        is_reversal = scoring.detect_reversal(candles, sweep)
        fake_breakout = scoring.detect_fake_breakout(candles)
        market_mode = scoring.get_market_mode(atr_ratio)
        
        confidence = scoring.calculate_confidence(
            trend, sweep, False, total_strength, False,
            htf_aligned=True,
            market_bias=None,
            is_reversal=is_reversal
        )
        
        confidence = scoring.apply_fake_breakout_bonus(confidence, fake_breakout, "BUY" if trend == "UPTREND" else "SELL")
        confidence = scoring.apply_adaptive_scoring(confidence, market_mode, sweep, "BUY" if trend == "UPTREND" else "SELL")
        
        if not liquidity_aligned:
            confidence = max(0, confidence - 20)
        else:
            confidence += 5
        
        if not volatility_pass:
            confidence -= 10
        elif atr_ratio > 0.01:
            confidence += 5
        
        if trend == "RANGE" and not is_reversal:
            confidence = max(0, confidence - 25)
        
        if trend == "RANGE" and is_reversal:
            confidence += 10
        
        confidence = max(0, min(confidence, 100))
        
        signal_type = "BUY" if trend == "UPTREND" else "SELL"
        
        entry_primary, entry_limit = refine_entry(candles, trend, pair)
        sl, risk_pct = calculate_atr_based_sl(entry_primary, candles, signal_type, pair)
        
        if not config.validate_trade(entry_primary, sl):
            return {
                "pair": pair,
                "signal": "NO TRADE",
                "confidence": confidence,
                "reason": "Invalid trade params"
            }
        
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
            "entry_primary": config.round_to_tick(pair, entry_primary),
            "entry_limit": config.round_to_tick(pair, entry_limit),
            "sl": config.round_to_tick(pair, sl),
            "tp1": config.round_to_tick(pair, tp1),
            "tp2": config.round_to_tick(pair, tp2),
            "tp3": config.round_to_tick(pair, tp3),
            "confidence": confidence,
            "trend": trend,
            "liquidity": sweep,
            "atr_ratio": atr_ratio,
            "risk_pct": risk_pct,
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        return {
            "pair": pair,
            "signal": "NO TRADE",
            "confidence": 0,
            "reason": f"Error: {str(e)}"
        }