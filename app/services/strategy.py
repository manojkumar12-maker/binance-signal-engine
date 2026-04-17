from typing import Dict, Optional, Tuple
from datetime import datetime
import logging
import config
from app.services import market, structure, liquidity, volume, scoring, bias_engine, regime, validation, whale
from app.services import extension_filter, entry_quality, fake_breakout_filter, mtf_alignment
from app.services import sniper_filter, volatility_compression, no_trade_zones, risk_engine
from app.services import data_consistency
from app.services.scoring import get_confidence_tier, check_location_filter, get_regime_enforcement

logger = logging.getLogger("signal_strategy")


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


def check_ltf_entry_trigger(candles_15m: list, trend: str) -> tuple:
    if not candles_15m or len(candles_15m) < 5:
        return False, "NO_DATA"
    
    recent = candles_15m[-5:]
    last = candles_15m[-1]
    prev = recent[-2]
    
    last_close = last.get('close', 0)
    last_open = last.get('open', 0)
    last_high = last.get('high', 0)
    last_low = last.get('low', 0)
    prev_high = prev.get('high', 0)
    prev_low = prev.get('low', 0)
    
    body = abs(last_close - last_open)
    candle_range = last_high - last_low
    body_ratio = body / candle_range if candle_range > 0 else 0
    
    if trend == "UPTREND":
        if last_high > prev_high and last_close > last_open:
            return True, "BREAKOUT"
        
        if last_low > prev_low and last_close > last_open and body_ratio > 0.6:
            return True, "REJECTION"
        
        return False, "NO_TRIGGER"
    
    elif trend == "DOWNTREND":
        if last_low < prev_low and last_close < last_open:
            return True, "BREAKOUT"
        
        if last_high < prev_high and last_close < last_open and body_ratio > 0.6:
            return True, "REJECTION"
        
        return False, "NO_TRIGGER"
    
    return False, "RANGE"


def check_m5_retest_entry(candles_5m: list, trend: str, entry_price: float, sl: float) -> bool:
    if not candles_5m or len(candles_5m) < 10:
        return True
    
    recent = candles_5m[-10:]
    
    if trend == "UPTREND":
        swing_lows = []
        for i in range(1, len(recent) - 1):
            if recent[i]["low"] < recent[i-1]["low"] and recent[i]["low"] < recent[i+1]["low"]:
                swing_lows.append(recent[i]["low"])
        
        if not swing_lows:
            return True
        
        recent_low = min(swing_lows)
        
        if recent_low > sl and recent_low < entry_price:
            return True
        
        return False
    
    elif trend == "DOWNTREND":
        swing_highs = []
        for i in range(1, len(recent) - 1):
            if recent[i]["high"] > recent[i-1]["high"] and recent[i]["high"] > recent[i+1]["high"]:
                swing_highs.append(recent[i]["high"])
        
        if not swing_highs:
            return True
        
        recent_high = max(swing_highs)
        
        if recent_high < sl and recent_high > entry_price:
            return True
        
        return False
    
    return True


def classify_setup_type(bos: Optional[str], choch: Optional[str], sweep: Optional[str], trend: str = "RANGE") -> str:
    if choch and "CHoCH" in choch and sweep and "REJECTION" in sweep:
        return "REVERSAL_STRONG"
    
    if choch and "CHoCH" in choch:
        return "REVERSAL_WEAK"
    
    if bos and "BOS" in bos and trend != "RANGE":
        return "CONTINUATION"
    
    if bos and "BOS" in bos:
        return "CONTINUATION"
    
    if sweep:
        return "SWEEP_PLAY"
    
    return "WEAK_SETUP"


def validate_retest(candles_5m: list, trend: str) -> bool:
    if not candles_5m or len(candles_5m) < 10:
        return True
    
    recent = candles_5m[-5:]
    last = recent[-1]
    prev = recent[-2]
    
    body = abs(last.get('close', 0) - last.get('open', 0))
    range_ = last.get('high', 0) - last.get('low', 0)
    
    if range_ == 0:
        return False
    
    body_ratio = body / range_
    
    if trend == "UPTREND":
        last_low = last.get('low', 0)
        prev_low = prev.get('low', 0)
        
        if last_low > prev_low:
            if body_ratio > 0.6:
                return True
        return False
    
    elif trend == "DOWNTREND":
        last_high = last.get('high', 0)
        prev_high = prev.get('high', 0)
        
        if last_high < prev_high:
            if body_ratio > 0.6:
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
        ltf_candles_5m = market.get_klines(pair, "5m", config.CANDLE_LIMIT)
        
        if htf_candles_4h and len(htf_candles_4h) >= 20:
            htf_candles_4h = data_consistency.get_closed_candles(htf_candles_4h, remove_last=1)
        
        if ltf_candles_15m and len(ltf_candles_15m) >= 20:
            ltf_candles_15m = data_consistency.get_closed_candles(ltf_candles_15m, remove_last=1)
        
        if ltf_candles_5m and len(ltf_candles_5m) >= 20:
            ltf_candles_5m = data_consistency.get_closed_candles(ltf_candles_5m, remove_last=1)
        
        trend = structure.detect_trend(candles)
        htf_trend = structure.detect_htf_trend(htf_candles) if htf_candles else "RANGE"
        htf_trend_4h = structure.detect_htf_trend(htf_candles_4h) if htf_candles_4h else "RANGE"
        
        htf_aligned = True
        htf_mismatch_penalty = 0
        if htf_trend_4h != "RANGE" and htf_trend_4h != trend:
            htf_aligned = False
            htf_mismatch_penalty = 25
        
        ltf_trend = structure.detect_trend(ltf_candles_15m) if ltf_candles_15m else "RANGE"
        
        if ltf_candles_15m:
            ltf_bos = structure.detect_bos(ltf_candles_15m, trend)
            ltf_entry_trigger, ltf_trigger_type = check_ltf_entry_trigger(ltf_candles_15m, trend)
        else:
            ltf_bos = None
            ltf_entry_trigger = False
            ltf_trigger_type = "NO_DATA"
        
        sweep = liquidity.detect_sweep(candles)
        
        bos = structure.detect_bos(candles, trend)
        choch = structure.detect_choch(candles, trend)
        fvg = structure.detect_fvg(candles)
        is_chop = structure.is_chop_market(candles)
        liquidity_targets = structure.get_liquidity_targets(candles, "BUY" if trend == "UPTREND" else "SELL")
        vwap_bias = structure.get_vwap_bias(candles)
        
        m5_retest_valid = validate_retest(ltf_candles_5m, trend) if ltf_candles_5m else True
        
        setup_type = classify_setup_type(bos, choch, sweep, trend)
        
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
        
        chop_penalty = 0
        if not htf_aligned and htf_trend != "RANGE":
            htf_mismatch_penalty = 30
        
        if is_chop:
            chop_penalty = 35
        
        if not ltf_entry_trigger:
            logger.warning(f"[LTF] {pair}: No entry trigger ({ltf_trigger_type}) - allowing with penalty")
        
        if not liquidity_targets.get("rr_viable", True):
            logger.warning(f"[RR] {pair}: Poor liquidity target RR - applying penalty")
        
        vwap_penalty = 0
        if vwap_bias != "NEUTRAL":
            signal_direction = "BUY" if trend == "UPTREND" else "SELL"
            if vwap_bias == "BEARISH" and signal_direction == "BUY":
                vwap_penalty = 20
            if vwap_bias == "BULLISH" and signal_direction == "SELL":
                vwap_penalty = 20
        
        is_reversal = scoring.detect_reversal(candles, sweep)
        fake_breakout = scoring.detect_fake_breakout(candles)
        market_mode = scoring.get_market_mode(atr_ratio)
        
        liquidity_aligned = scoring.validate_liquidity(trend, sweep)
        
        whale_signal, whale_bonus = whale.detect_whale_activity(candles, oi_data)
        order_flow = whale.order_flow_strength(candles[-1])
        is_fake = whale.is_fake_breakout(candles)
        
        if total_strength < 3:
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
        
        from app.services.scoring import calculate_split_confidence
        
        entry_score_val = 70
        
        structure_score, execution_score, reject_reason = calculate_split_confidence(
            trend=trend,
            liquidity=sweep,
            htf_aligned=htf_aligned,
            bos=bos,
            choch=choch,
            setup_type=setup_type,
            volume_spike=volume_spike,
            whale_signal=whale_signal,
            order_flow=order_flow,
            fvg=fvg,
            ltf_trigger=ltf_entry_trigger,
            entry_score=entry_score_val,
            fake_breakout=fake_breakout,
            market_bias_aligned=True
        )
        
        if reject_reason:
            logger.warning(f"[SCORING] {pair}: {reject_reason} - structure={structure_score}, execution={execution_score}")
        
        if not liquidity_targets.get("rr_viable", True):
            structure_score -= 15
        
        structure_score -= vwap_penalty
        
        confidence = int(structure_score * 0.65 + execution_score * 0.35)
        
        current_session = structure.get_current_session()
        if current_session not in ["LONDON", "NY"]:
            confidence -= 5
        
        if not m5_retest_valid:
            confidence -= 5
        
        confidence = max(0, min(100, confidence))
        
        from app.services.scoring import calculate_adaptive_confidence
        adaptive_conf = calculate_adaptive_confidence({
            "liquidity": sweep,
            "bos": bos,
            "choch": choch,
            "fvg": fvg,
            "volume": volume_confirmed,
            "whale_signal": whale_signal,
            "trend": f"{trend} ({htf_trend})",
            "vwap_bias": vwap_bias,
            "setup_type": setup_type
        })
        
        if adaptive_conf > confidence:
            confidence = adaptive_conf
        
        confidence -= htf_mismatch_penalty
        confidence -= chop_penalty
        
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
        
        price_change = (candles[-1].get('close', 0) - candles[-2].get('close', 0)) / candles[-2].get('close', 1) if len(candles) >= 2 and candles[-2].get('close') else 0
        oi_change = 0
        if oi_data and isinstance(oi_data, list) and len(oi_data) >= 2:
            try:
                if all(isinstance(x, (int, float)) for x in oi_data):
                    oi_change = (oi_data[-1] - oi_data[-2]) / oi_data[-2] if oi_data[-2] > 0 else 0
            except:
                pass
        
        if price_change > 0 and oi_change < 0:
            confidence -= 10
        elif price_change > 0 and oi_change > 0:
            confidence += 5
        elif price_change < 0 and oi_change > 0:
            confidence -= 10
        elif price_change < 0 and oi_change > 0:
            confidence += 5
        
        signal_type = "BUY" if trend == "UPTREND" else "SELL"
        
        entry_primary, entry_limit = refine_entry(candles, trend, pair)
        
        sl, risk_pct = calculate_atr_based_sl(entry_primary, candles, signal_type, pair)
        
        is_extended, extension_distance = extension_filter.check_extension(candles, timeframe)
        
        if is_extended:
            confidence -= 15
        
        is_trap, trap_details = fake_breakout_filter.detect_fake_breakout_trap(candles)
        if is_trap:
            confidence = max(0, confidence - 15)
        
        no_trade, zone_details = no_trade_zones.check_no_trade_zones(candles)
        if no_trade:
            confidence -= 10
        
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
        
        is_compressed, _ = volatility_compression.detect_volatility_compression(candles)
        
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
            confidence -= 30
        
        location_ok, location_reason = check_location_filter(candles, signal_type, entry_primary)
        if not location_ok:
            confidence -= 15
        
        regime_ok, regime_reason = get_regime_enforcement(detected_regime, signal_type, is_reversal)
        if not regime_ok:
            confidence -= 15
        
        current_session = structure.get_current_session()
        
        stacked_ob = structure.detect_multi_tf_ob(htf_candles_4h, candles)
        
        tier = get_confidence_tier(int(confidence), int(entry_score))
        
        if config.SNIPER_MODE_ONLY and tier != "SNIPER":
            confidence -= 20
        
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
            confidence -= 20
        
        confidence = max(0, min(100, confidence))
        
        logger.info(f"[SIGNAL] {pair}: confidence={confidence}, tier={tier}, setup={setup_type}, trend={trend}")
        
        if confidence < 15:
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
                "reason": "Confidence below threshold"
            }
        
        return {
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
            "tier": tier,
            "structure_score": structure_score,
            "execution_score": execution_score,
            "bos": bos,
            "choch": choch,
            "fvg": fvg,
            "is_chop": is_chop,
            "liquidity_target": liquidity_targets.get("target"),
            "vwap_bias": vwap_bias,
            "htf_trend_4h": htf_trend_4h,
            "ltf_trend_15m": ltf_trend,
            "ltf_entry_trigger": ltf_entry_trigger,
            "setup_type": setup_type,
            "m5_retest_valid": m5_retest_valid,
            "stacked_ob": stacked_ob.get("type") if stacked_ob else None,
            "current_session": current_session,
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
        
        if trend == "RANGE":
            if is_reversal or sweep:
                confidence += 10
                logger.info(f"[SIGNAL_GEN] {pair}: RANGE with reversal/liq - bonus")
            else:
                confidence = max(0, confidence - 10)
                logger.info(f"[SIGNAL_GEN] {pair}: RANGE flat - penalty")
        else:
            if is_reversal or sweep:
                confidence = min(100, confidence + 10)
        
        confidence = max(0, min(confidence, 100))
        
        logger.info(f"[SIGNAL_GEN] {pair}: trend={trend}, confidence={confidence}, liquidity={sweep}, vol_pass={volatility_pass}, atr={atr_ratio:.6f}")
        
        signal_type = "BUY" if trend == "UPTREND" else "SELL"
        
        entry_primary, entry_limit = refine_entry(candles, trend, pair)
        sl, risk_pct = calculate_atr_based_sl(entry_primary, candles, signal_type, pair)
        
        entry_score = 70
        if liquidity_aligned:
            entry_score += 5
        if order_flow > 0.6:
            entry_score += 10
        elif order_flow > 0.4:
            entry_score += 5
        if fake_breakout:
            entry_score += 10
        if is_reversal:
            entry_score += 10
        entry_score = min(100, entry_score)
        
        tier = get_confidence_tier(int(confidence), int(entry_score))
        
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
        
        atr = calculate_atr(candles)
        
        if config.ATR_BASED_TP_SL and atr > 0:
            tp1_distance = atr * config.ATR_TP1_MULTIPLIER
            tp2_distance = atr * config.ATR_TP2_MULTIPLIER
            tp3_distance = atr * config.ATR_TP3_MULTIPLIER
            
            if signal_type == "BUY":
                tp1 = entry_primary + tp1_distance
                tp2 = entry_primary + tp2_distance
                tp3 = entry_primary + tp3_distance
            else:
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
        
        from app.services.structure import get_liquidity_targets
        liq_targets = get_liquidity_targets(candles, signal_type, 20)
        liq_target = liq_targets.get("target")
        
        if liq_target:
            if signal_type == "BUY" and liq_target > entry_primary:
                tp1 = min(liq_target * 0.95, entry_primary * (1 + config.TP1_PERCENT))
                tp2 = liq_target * 0.90
                tp3 = liq_target * 0.85
            elif signal_type == "SELL" and liq_target < entry_primary:
                tp1 = max(liq_target * 1.05, entry_primary * (1 - config.TP1_PERCENT))
                tp2 = liq_target * 1.10
                tp3 = liq_target * 1.15
        
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
                "risk_pct": round(abs(entry_primary - sl) / entry_primary * 100, 2),
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
            "entry_score": entry_score,
            "tier": tier,
            "trend": trend,
            "setup_type": "CONTINUATION" if trend != "RANGE" else "RANGE",
            "liquidity": sweep,
            "atr_ratio": atr_ratio,
            "risk_pct": round(abs(entry_primary - sl) / entry_primary * 100, 2),
            "regime": detected_regime,
            "signal_type": signal_type_value,
            "is_reversal": is_reversal,
            "fake_breakout": fake_breakout,
            "whale_signal": whale_signal,
            "order_flow": round(order_flow, 2),
            "bos": "CONTINUATION" if trend != "RANGE" else "RANGE",
            "choch": "REVERSAL" if is_reversal else None,
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        return {
            "pair": pair,
            "signal": "NO TRADE",
            "confidence": 0,
            "reason": f"Error: {str(e)}"
        }