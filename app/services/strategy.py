from typing import Dict, Optional, Tuple
from datetime import datetime
import config
from app.services import market, structure, liquidity, volume, scoring, bias_engine, regime, validation, whale
from app.services import extension_filter, entry_quality, fake_breakout_filter, mtf_alignment
from app.services import sniper_filter, volatility_compression, no_trade_zones, risk_engine
from app.services import data_consistency
from app.services.scoring import get_confidence_tier, check_location_filter, get_regime_enforcement


def calculate_atr(candles: list, period: int = 14) -> float:
    return volume.calculate_atr(candles, period)


def calculate_atr_based_sl(entry: float, candles: list, signal_type: str, pair: str = "BTCUSDT") -> Tuple[float, float]:
    atr = calculate_atr(candles)
    sl_distance = atr * config.ATR_SL_MULTIPLIER
    
    min_sl_distance = entry * 0.003
    if sl_distance < min_sl_distance:
        sl_distance = min_sl_distance
    
    if signal_type == "BUY":
        sl = entry - sl_distance
    else:
        sl = entry + sl_distance
    
    risk_pct = round(abs(entry - sl) / entry * 100, 2)
    
    return sl, risk_pct


def check_ltf_entry_trigger(candles_15m: list, trend: str) -> bool:
    if not candles_15m or len(candles_15m) < 5:
        return False
    
    recent = candles_15m[-5:]
    last = candles_15m[-1]
    
    if trend == "UPTREND":
        last_high = last.get('high', 0)
        prev_high = recent[-2].get('high', 0)
        
        if last.get('close', 0) > last.get('open', 0):
            if last_high > prev_high:
                return True
        return False
    
    elif trend == "DOWNTREND":
        last_low = last.get('low', 0)
        prev_low = recent[-2].get('low', 0)
        
        if last.get('close', 0) < last.get('open', 0):
            if last_low < prev_low:
                return True
        return False
    
    return False


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


def generate_signal(pair: str, timeframe: str = "1h", fetch_oi: bool = True, use_bias: bool = True, use_closed_candles: bool = True) -> Dict:
    try:
        candles = market.get_klines(pair, timeframe, config.CANDLE_LIMIT)
        htf_candles = market.get_klines(pair, "4h", config.CANDLE_LIMIT)
        
        if use_closed_candles:
            candles = data_consistency.get_closed_candles(candles, remove_last=1)
            htf_candles = data_consistency.get_closed_candles(htf_candles, remove_last=1)
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
        
        htf_candles_4h = market.get_klines(pair, "4h", config.CANDLE_LIMIT)
        ltf_candles_15m = market.get_klines(pair, "15m", config.CANDLE_LIMIT)
        
        if htf_candles_4h and len(htf_candles_4h) >= 20:
            htf_candles_4h = data_consistency.get_closed_candles(htf_candles_4h, remove_last=1)
        
        if ltf_candles_15m and len(ltf_candles_15m) >= 20:
            ltf_candles_15m = data_consistency.get_closed_candles(ltf_candles_15m, remove_last=1)
        
        trend = structure.detect_trend(candles)
        htf_trend = structure.detect_htf_trend(htf_candles) if htf_candles else "RANGE"
        htf_trend_4h = structure.detect_htf_trend(htf_candles_4h) if htf_candles_4h else "RANGE"
        
        if htf_trend_4h != "RANGE" and htf_trend_4h != trend:
            return {
                "pair": pair,
                "signal": "NO TRADE",
                "entry_primary": current_price, "entry_limit": 0,
                "sl": 0, "tp1": 0, "tp2": 0, "tp3": 0,
                "confidence": 0,
                "trend": f"{trend} ({htf_trend}/{htf_trend_4h})",
                "liquidity": None,
                "volume": False,
                "atr_ratio": 0,
                "timestamp": datetime.utcnow().isoformat(),
                "reason": "H4_H1_MISMATCH"
            }
        
        ltf_trend = structure.detect_trend(ltf_candles_15m) if ltf_candles_15m else "RANGE"
        
        if ltf_candles_15m:
            ltf_bos = structure.detect_bos(ltf_candles_15m, trend)
            ltf_entry_trigger = check_ltf_entry_trigger(ltf_candles_15m, trend)
        else:
            ltf_bos = None
            ltf_entry_trigger = False
        
        sweep = liquidity.detect_sweep(candles)
        
        bos = structure.detect_bos(candles, trend)
        choch = structure.detect_choch(candles, trend)
        fvg = structure.detect_fvg(candles)
        is_chop = structure.is_chop_market(candles)
        liquidity_targets = structure.get_liquidity_targets(candles, "BUY" if trend == "UPTREND" else "SELL")
        vwap_bias = structure.get_vwap_bias(candles)
        
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
        
        if not htf_aligned and htf_trend != "RANGE":
            return {
                "pair": pair,
                "signal": "NO TRADE",
                "entry_primary": current_price, "entry_limit": 0,
                "sl": 0, "tp1": 0, "tp2": 0, "tp3": 0,
                "confidence": 0,
                "trend": f"{trend} ({htf_trend})",
                "liquidity": sweep,
                "volume": volume_confirmed,
                "atr_ratio": atr_ratio,
                "timestamp": datetime.utcnow().isoformat(),
                "reason": "HTF_LTF_MISMATCH"
            }
        
        if is_chop:
            return {
                "pair": pair,
                "signal": "NO TRADE",
                "entry_primary": current_price, "entry_limit": 0,
                "sl": 0, "tp1": 0, "tp2": 0, "tp3": 0,
                "confidence": 0,
                "trend": f"{trend} ({htf_trend})",
                "liquidity": sweep,
                "volume": volume_confirmed,
                "atr_ratio": atr_ratio,
                "timestamp": datetime.utcnow().isoformat(),
                "reason": "CHOP_MARKET"
            }
        
        if not ltf_entry_trigger:
            return {
                "pair": pair,
                "signal": "NO TRADE",
                "entry_primary": current_price, "entry_limit": 0,
                "sl": 0, "tp1": 0, "tp2": 0, "tp3": 0,
                "confidence": 0,
                "trend": f"{trend} ({htf_trend})",
                "liquidity": sweep,
                "volume": volume_confirmed,
                "atr_ratio": atr_ratio,
                "timestamp": datetime.utcnow().isoformat(),
                "reason": "NO_LTF_ENTRY_TRIGGER"
            }
        
        if not liquidity_targets.get("rr_viable", True):
            return {
                "pair": pair,
                "signal": "NO TRADE",
                "entry_primary": current_price, "entry_limit": 0,
                "sl": 0, "tp1": 0, "tp2": 0, "tp3": 0,
                "confidence": 0,
                "trend": f"{trend} ({htf_trend})",
                "liquidity": sweep,
                "volume": volume_confirmed,
                "atr_ratio": atr_ratio,
                "timestamp": datetime.utcnow().isoformat(),
                "reason": "POOR_LIQUIDITY_TARGET_RR"
            }
        
        if vwap_bias != "NEUTRAL":
            signal_direction = "BUY" if trend == "UPTREND" else "SELL"
            if vwap_bias == "BEARISH" and signal_direction == "BUY":
                return {
                    "pair": pair,
                    "signal": "NO TRADE",
                    "entry_primary": current_price, "entry_limit": 0,
                    "sl": 0, "tp1": 0, "tp2": 0, "tp3": 0,
                    "confidence": 0,
                    "trend": f"{trend} ({htf_trend})",
                    "liquidity": sweep,
                    "volume": volume_confirmed,
                    "atr_ratio": atr_ratio,
                    "timestamp": datetime.utcnow().isoformat(),
                    "reason": f"VWAP_MISMATCH: price={vwap_bias}"
                }
            if vwap_bias == "BULLISH" and signal_direction == "SELL":
                return {
                    "pair": pair,
                    "signal": "NO TRADE",
                    "entry_primary": current_price, "entry_limit": 0,
                    "sl": 0, "tp1": 0, "tp2": 0, "tp3": 0,
                    "confidence": 0,
                    "trend": f"{trend} ({htf_trend})",
                    "liquidity": sweep,
                    "volume": volume_confirmed,
                    "atr_ratio": atr_ratio,
                    "timestamp": datetime.utcnow().isoformat(),
                    "reason": f"VWAP_MISMATCH: price={vwap_bias}"
                }
        
        is_reversal = scoring.detect_reversal(candles, sweep)
        
        fake_breakout = scoring.detect_fake_breakout(candles)
        market_mode = scoring.get_market_mode(atr_ratio)
        
        liquidity_aligned = scoring.validate_liquidity(trend, sweep)
        
        whale_signal, whale_bonus = whale.detect_whale_activity(candles, oi_data)
        order_flow = whale.order_flow_strength(candles[-1])
        is_fake = whale.is_fake_breakout(candles)
        
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
        
        if bos:
            confidence += 15
        
        if choch:
            confidence += 20
        
        if fvg:
            confidence += 5
        
        confidence = scoring.apply_fake_breakout_bonus(confidence, fake_breakout, "BUY" if trend == "UPTREND" else "SELL")
        confidence = scoring.apply_adaptive_scoring(confidence, market_mode, sweep, "BUY" if trend == "UPTREND" else "SELL")
        
        confidence += whale_bonus
        
        if order_flow < 0.4:
            confidence -= 10
        elif order_flow > 0.7:
            confidence += 8
        
        if is_fake:
            confidence -= 25
        
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
        
        atr = calculate_atr(candles)
        
        recent_lows = [c['low'] for c in candles[-10:]]
        recent_highs = [c['high'] for c in candles[-10:]]
        support = min(recent_lows) if recent_lows else None
        resistance = max(recent_highs) if recent_highs else None
        
        candle_range = candles[-1].get('high', 0) - candles[-1].get('low', 0)
        avg_range = sum(c.get('high', 0) - c.get('low', 0) for c in candles[-20:]) / 20 if len(candles) >= 20 else candle_range
        
        if signal_type == "BUY" and support:
            if abs(entry_primary - support) < atr * 0.5:
                confidence += 15
            elif resistance and abs(entry_primary - resistance) < atr * 0.5:
                confidence -= 20
        elif signal_type == "SELL" and resistance:
            if abs(entry_primary - resistance) < atr * 0.5:
                confidence += 15
            elif support and abs(entry_primary - support) < atr * 0.5:
                confidence -= 20
        
        if candle_range > avg_range * 1.8:
            confidence += 10
        else:
            confidence -= 5
        
        if atr_ratio < 0.005:
            confidence -= 20
        
        price_change = (candles[-1].get('close', 0) - candles[-2].get('close', 0)) / candles[-2].get('close', 1) if len(candles) >= 2 and candles[-2].get('close') else 0
        oi_change = 0
        if oi_data and isinstance(oi_data, list) and len(oi_data) >= 2:
            try:
                if all(isinstance(x, (int, float)) for x in oi_data):
                    oi_change = (oi_data[-1] - oi_data[-2]) / oi_data[-2] if oi_data[-2] > 0 else 0
            except:
                pass
        
        if price_change > 0 and oi_change < 0:
            confidence -= 15
        elif price_change > 0 and oi_change > 0:
            confidence += 10
        elif price_change < 0 and oi_change > 0:
            confidence -= 15
        elif price_change < 0 and oi_change > 0:
            confidence += 10
        
        signal_type = "BUY" if trend == "UPTREND" else "SELL"
        
        entry_primary, entry_limit = refine_entry(candles, trend, pair)
        
        sl, risk_pct = calculate_atr_based_sl(entry_primary, candles, signal_type, pair)
        
        is_extended, extension_distance = extension_filter.check_extension(candles, timeframe)
        
        if is_extended:
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
                "is_extended": True,
                "extension_distance_pct": extension_distance,
                "timestamp": datetime.utcnow().isoformat(),
                "reason": f"MARKET EXTENDED: price {extension_distance}% from EMA25"
            }
        
        if atr_ratio < 0.005:
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
                "timestamp": datetime.utcnow().isoformat(),
                "reason": "CHOP MARKET: low volatility"
            }
        
        is_trap, trap_details = fake_breakout_filter.detect_fake_breakout_trap(candles)
        if is_trap:
            confidence = max(0, confidence - 25)
        
        no_trade, zone_details = no_trade_zones.check_no_trade_zones(candles)
        if no_trade:
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
                "timestamp": datetime.utcnow().isoformat(),
                "reason": f"NO_TRADE_ZONE: {zone_details.get('status')}"
            }
        
        entry_score, entry_breakdown = entry_quality.calculate_entry_quality_score(
            candles, signal_type, entry_primary, sl, 0
        )
        
        atr = calculate_atr(candles)
        
        if config.ATR_BASED_TP_SL:
            sl_distance = atr * config.ATR_SL_MULTIPLIER
            tp1_distance = atr * config.ATR_TP1_MULTIPLIER
            tp2_distance = atr * config.ATR_TP2_MULTIPLIER
            tp3_distance = atr * config.ATR_TP3_MULTIPLIER
            
            if signal_type == "BUY":
                sl = entry_primary - sl_distance
                tp1 = entry_primary + tp1_distance
                tp2 = entry_primary + tp2_distance
                tp3 = entry_primary + tp3_distance
            else:
                sl = entry_primary + sl_distance
                tp1 = entry_primary - tp1_distance
                tp2 = entry_primary - tp2_distance
                tp3 = entry_primary - tp3_distance
        else:
            if signal_type == "BUY":
                tp1 = entry_primary * (1 + config.TP1_PERCENT)
                tp2 = entry_primary * (1 + config.TP2_PERCENT)
                tp3 = entry_primary * (1 + config.TP3_PERCENT)
            else:
                tp1 = entry_primary * (1 - config.TP1_PERCENT)
                tp2 = entry_primary * (1 - config.TP2_PERCENT)
                tp3 = entry_primary * (1 - config.TP3_PERCENT)
        
        entry_score, entry_breakdown = entry_quality.calculate_entry_quality_score(
            candles, signal_type, entry_primary, sl, tp1
        )
        
        is_compressed, compression_details = volatility_compression.detect_volatility_compression(candles)
        if is_compressed:
            confidence += 10
        
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
        
        trend_strength = structure.detect_trend_strength(candles)
        detected_regime = regime.detect_market_regime(atr_ratio, trend, trend_strength)
        regime_config = regime.get_regime_config(detected_regime)
        
        if detected_regime == "LOW_VOL":
            return {
                "pair": pair,
                "signal": "NO TRADE",
                "entry_primary": entry_primary,
                "entry_limit": entry_limit,
                "sl": sl,
                "tp1": tp1, "tp2": tp2, "tp3": tp3,
                "confidence": confidence,
                "trend": f"{trend} ({htf_trend})",
                "liquidity": sweep,
                "volume": volume_confirmed,
                "atr_ratio": atr_ratio,
                "risk_pct": risk_pct,
                "regime": detected_regime,
                "signal_type": "CONTINUATION",
                "timestamp": datetime.utcnow().isoformat(),
                "reason": "LOW_VOL regime - insufficient volatility"
            }
        
        location_ok, location_reason = check_location_filter(candles, signal_type, entry_primary)
        if not location_ok:
            return {
                "pair": pair,
                "signal": "NO TRADE",
                "entry_primary": entry_primary,
                "entry_limit": entry_limit,
                "sl": sl,
                "tp1": tp1, "tp2": tp2, "tp3": tp3,
                "confidence": confidence,
                "trend": f"{trend} ({htf_trend})",
                "liquidity": sweep,
                "volume": volume_confirmed,
                "atr_ratio": atr_ratio,
                "risk_pct": risk_pct,
                "regime": detected_regime,
                "signal_type": signal_type,
                "timestamp": datetime.utcnow().isoformat(),
                "reason": f"LOCATION_FILTER: {location_reason}"
            }
        
        regime_ok, regime_reason = get_regime_enforcement(detected_regime, signal_type, is_reversal)
        if not regime_ok:
            return {
                "pair": pair,
                "signal": "NO TRADE",
                "entry_primary": entry_primary,
                "entry_limit": entry_limit,
                "sl": sl,
                "tp1": tp1, "tp2": tp2, "tp3": tp3,
                "confidence": confidence,
                "trend": f"{trend} ({htf_trend})",
                "liquidity": sweep,
                "volume": volume_confirmed,
                "atr_ratio": atr_ratio,
                "risk_pct": risk_pct,
                "regime": detected_regime,
                "signal_type": signal_type,
                "timestamp": datetime.utcnow().isoformat(),
                "reason": f"REGIME_ENFORCEMENT: {regime_reason}"
            }
        
        tier = get_confidence_tier(int(confidence), int(entry_score))
        
        if config.SNIPER_MODE_ONLY and tier != "SNIPER":
            return {
                "pair": pair,
                "signal": "NO TRADE",
                "entry_primary": entry_primary,
                "entry_limit": entry_limit,
                "sl": sl,
                "tp1": tp1, "tp2": tp2, "tp3": tp3,
                "confidence": confidence,
                "trend": f"{trend} ({htf_trend})",
                "liquidity": sweep,
                "volume": volume_confirmed,
                "atr_ratio": atr_ratio,
                "risk_pct": risk_pct,
                "regime": detected_regime,
                "signal_type": signal_type,
                "tier": tier,
                "timestamp": datetime.utcnow().isoformat(),
                "reason": f"TIER_REJECT: {tier} requires SNIPER for execution"
            }
        
        signal_type_value = validation.classify_signal_type({
            "is_reversal": is_reversal,
            "fake_breakout": fake_breakout
        })
        
        is_valid, validation_reason = validation.validate_signal({
            "signal": signal_type,
            "trend": trend,
            "entry_primary": entry_primary,
            "sl": sl,
            "risk_pct": risk_pct,
            "confidence": confidence,
            "atr_ratio": atr_ratio
        })
        
        if not is_valid:
            return {
                "pair": pair,
                "signal": "NO TRADE",
                "entry_primary": entry_primary,
                "entry_limit": entry_limit,
                "sl": sl,
                "tp1": tp1, "tp2": tp2, "tp3": tp3,
                "confidence": confidence,
                "trend": f"{trend} ({htf_trend})",
                "liquidity": sweep,
                "volume": volume_confirmed,
                "atr_ratio": atr_ratio,
                "risk_pct": risk_pct,
                "regime": detected_regime,
                "signal_type": signal_type_value,
                "timestamp": datetime.utcnow().isoformat(),
                "reason": validation_reason
            }
        
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
            "regime": detected_regime,
            "signal_type": signal_type_value,
            "whale_signal": whale_signal,
            "order_flow": round(order_flow, 2),
            "entry_score": entry_score,
            "entry_breakdown": entry_breakdown,
            "is_extended": is_extended,
            "extension_distance_pct": extension_distance,
            "fake_breakout_trap": is_trap,
            "compression_signal": is_compressed,
            "tier": tier,
            "bos": bos,
            "choch": choch,
            "fvg": fvg,
            "is_chop": is_chop,
            "liquidity_target": liquidity_targets.get("target"),
            "vwap_bias": vwap_bias,
            "htf_trend_4h": htf_trend_4h,
            "ltf_trend_15m": ltf_trend,
            "ltf_entry_trigger": ltf_entry_trigger,
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
        
        oi_data = market.get_open_interest(pair) if hasattr(market, 'get_open_interest') else []
        
        whale_signal, whale_bonus = whale.detect_whale_activity(candles, oi_data)
        order_flow = whale.order_flow_strength(candles[-1])
        is_fake = whale.is_fake_breakout(candles)
        
        confidence = scoring.calculate_confidence(
            trend, sweep, False, total_strength, False,
            htf_aligned=True,
            market_bias=None,
            is_reversal=is_reversal
        )
        
        confidence = scoring.apply_fake_breakout_bonus(confidence, fake_breakout, "BUY" if trend == "UPTREND" else "SELL")
        confidence = scoring.apply_adaptive_scoring(confidence, market_mode, sweep, "BUY" if trend == "UPTREND" else "SELL")
        
        confidence += whale_bonus
        
        if order_flow < 0.4:
            confidence -= 10
        elif order_flow > 0.7:
            confidence += 8
        
        if is_fake:
            confidence -= 25
        
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
        
        trend_strength = structure.detect_trend_strength(candles)
        detected_regime = regime.detect_market_regime(atr_ratio, trend, trend_strength)
        
        signal_type_value = validation.classify_signal_type({
            "is_reversal": is_reversal,
            "fake_breakout": fake_breakout
        })
        
        is_valid, validation_reason = validation.validate_signal({
            "signal": signal_type,
            "trend": trend,
            "entry_primary": entry_primary,
            "sl": sl,
            "risk_pct": risk_pct,
            "confidence": confidence,
            "atr_ratio": atr_ratio
        })
        
        if signal_type == "BUY":
            tp1 = entry_primary * (1 + config.TP1_PERCENT)
            tp2 = entry_primary * (1 + config.TP2_PERCENT)
            tp3 = entry_primary * (1 + config.TP3_PERCENT)
        else:
            tp1 = entry_primary * (1 - config.TP1_PERCENT)
            tp2 = entry_primary * (1 - config.TP2_PERCENT)
            tp3 = entry_primary * (1 - config.TP3_PERCENT)
        
        if not is_valid:
            return {
                "pair": pair,
                "signal": "NO TRADE",
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
                "regime": detected_regime,
                "signal_type": signal_type_value,
                "timestamp": datetime.utcnow().isoformat(),
                "reason": validation_reason
            }
        
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
            "regime": detected_regime,
            "signal_type": signal_type_value,
            "is_reversal": is_reversal,
            "fake_breakout": fake_breakout,
            "whale_signal": whale_signal,
            "order_flow": round(order_flow, 2),
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        return {
            "pair": pair,
            "signal": "NO TRADE",
            "confidence": 0,
            "reason": f"Error: {str(e)}"
        }