from typing import Optional, Dict, List
import logging
import config

logger = logging.getLogger("scoring_debug")

WEIGHTS = {
    "trend": 10,
    "liquidity": 20,
    "volume": 15,
    "fake_breakout": 25,
    "whale": 20,
    "order_flow": 10
}

WEIGHTED_WEIGHTS = {
    "trend_strength": 0.25,
    "volume_strength": 0.20,
    "liquidity_signal": 0.15,
    "whale_signal": 0.15,
    "entry_score": 0.15,
    "regime_alignment": 0.10
}


def calculate_confidence(
    trend: str, 
    liquidity: Optional[str], 
    volume: bool, 
    strength: int = 0, 
    volume_spike: bool = False,
    htf_aligned: bool = True,
    market_bias: Optional[Dict] = None,
    is_reversal: bool = False,
    fake_breakout: bool = False,
    whale_signal: str = "NEUTRAL",
    order_flow: float = 0.5,
    signal_type: str = "CONTINUATION",
    debug: bool = False
) -> int:
    score = 30
    reasons = []
    
    if trend != "RANGE":
        score += WEIGHTS["trend"]
    else:
        reasons.append("RANGE_TREND")
        score -= 20
    
    if htf_aligned:
        score += 8
    else:
        if liquidity and "REJECTION" in liquidity:
            score += 5
        else:
            score -= 12
    
    if liquidity is not None:
        if "REJECTION" in liquidity:
            score += WEIGHTS["liquidity"]
        else:
            score += 5
    else:
        score -= 10
        reasons.append("NO_LIQUIDITY")
    
    if volume_spike:
        score += WEIGHTS["volume"]
    else:
        score += 2
    
    score += min(strength, 8)
    
    if fake_breakout:
        if is_reversal or signal_type == "REVERSAL":
            score += 20
        else:
            score -= WEIGHTS["fake_breakout"]
            reasons.append("FAKE_BREAKOUT_BAD")
    
    if whale_signal != "NEUTRAL":
        if whale_signal in ["ACCUMULATION", "DISTRIBUTION"]:
            score += WEIGHTS["whale"]
    
    if order_flow > 0.7:
        score += WEIGHTS["order_flow"]
    elif order_flow < 0.4:
        score -= 10
        reasons.append("WEAK_ORDER_FLOW")
    
    if not liquidity:
        score -= 20
    
    if market_bias:
        bias = market_bias.get("bias", "NEUTRAL")
        signal = "BUY" if trend == "UPTREND" else "SELL"
        
        if bias == "BULLISH" and signal == "BUY":
            score += 8
        elif bias == "BEARISH" and signal == "SELL":
            score += 8
        elif bias in ["BULLISH", "BEARISH"]:
            score -= 20
            reasons.append("BIAS_MISMATCH")
    
    if liquidity != "REJECTION" and not fake_breakout and order_flow < 0.6:
        reasons.append("WEAK_SETUP")
    
    score = max(0, min(score, 92))
    
    if debug:
        logger.info(f"SCORE={score} | REASONS={reasons}")
    
    return score


def detect_reversal(candles: List[Dict], sweep_type: Optional[str]) -> bool:
    if not sweep_type or "REJECTION" not in sweep_type:
        if len(candles) >= 2:
            last = candles[-1]
            prev = candles[-2]
            if abs(last['close'] - prev['close']) / prev['close'] > 0.008:
                return True
        return False
    
    if len(candles) < 2:
        return True
    
    last = candles[-1]
    prev = candles[-2]
    
    if sweep_type == "SWEEP_LOW_REJECTION":
        return last['close'] > prev['close']
    elif sweep_type == "SWEEP_HIGH_REJECTION":
        return last['close'] < prev['close']
    
    return True


def detect_fake_breakout(candles: List[Dict]) -> Optional[str]:
    if len(candles) < 2:
        return None
    
    last = candles[-1]
    prev = candles[-2]
    
    high = last["high"]
    low = last["low"]
    close = last["close"]
    open_ = last["open"]
    
    prev_high = prev["high"]
    prev_low = prev["low"]
    
    body = abs(close - open_)
    range_ = high - low
    
    if range_ == 0:
        return None
    
    body_ratio = body / range_
    
    if high > prev_high and close < prev_high and body_ratio < 0.4:
        return "FAKE_BREAKOUT_HIGH"
    
    if low < prev_low and close > prev_low and body_ratio < 0.4:
        return "FAKE_BREAKOUT_LOW"
    
    return None


def get_market_mode(atr_ratio: float) -> str:
    if atr_ratio > 0.01:
        return "TRENDING"
    elif atr_ratio < 0.003:
        return "RANGING"
    return "NORMAL"


def apply_adaptive_scoring(
    score: int,
    market_mode: str,
    liquidity: Optional[str],
    signal: str
) -> int:
    if market_mode == "TRENDING":
        score += 10
    elif market_mode == "RANGING":
        if liquidity is not None:
            score += 10
    
    return score


def apply_fake_breakout_bonus(
    score: int,
    fakeout: Optional[str],
    signal: str
) -> int:
    if fakeout == "FAKE_BREAKOUT_LOW" and signal == "BUY":
        return score + 20
    elif fakeout == "FAKE_BREAKOUT_HIGH" and signal == "SELL":
        return score + 20
    return score


def validate_liquidity(trend: str, sweep: Optional[str]) -> bool:
    if not sweep:
        return False
    
    if trend == "UPTREND":
        return sweep in ["SWEEP_LOW", "SWEEP_LOW_REJECTION", "SWEEP_HIGH_REJECTION"]
    
    if trend == "DOWNTREND":
        return sweep in ["SWEEP_HIGH", "SWEEP_HIGH_REJECTION", "SWEEP_LOW_REJECTION"]
    
    return False


def final_validation(signal: Dict) -> bool:
    entry = signal.get("entry_primary", 0)
    sl = signal.get("sl", 0)
    tp1 = signal.get("tp1", 0)
    trend = signal.get("trend", "")
    liquidity = signal.get("liquidity")
    
    if entry <= 0:
        return False
    
    if not config.min_price_filter(entry):
        return False
    
    if sl == entry:
        return False
    
    if tp1 == entry:
        return False
    
    if "RANGE" in trend and "REVERSAL" not in trend:
        return False
    
    if liquidity is None:
        return False
    
    risk_pct = abs(entry - sl) / entry
    if risk_pct < 0.002 or risk_pct > 0.02:
        return False
    
    return True


def calculate_score(trend: str, sweep: Optional[str], volume_confirmed: bool, candle_strength: int) -> int:
    score = 0
    
    if trend == "RANGE":
        return 0
    score += 25
    
    if not sweep:
        return 0
    
    if "REJECTION" in sweep:
        score += 30
    else:
        score += 20
    
    if volume_confirmed:
        score += 25
    else:
        score += 5
    
    score += min(20, candle_strength)
    
    return score


def get_signal_quality(score: int) -> str:
    if score >= 65:
        return "STRONG"
    elif score >= 50:
        return "WEAK"
    else:
        return "SKIP"


def get_confidence_tier(confidence: int, entry_score: int = 0) -> str:
    if confidence >= 85 and entry_score >= 80:
        return "SNIPER"
    elif confidence >= 78 and entry_score >= 70:
        return "A"
    elif confidence >= 70:
        return "B"
    else:
        return "REJECT"


def check_location_filter(candles: list, signal_type: str, current_price: float) -> tuple:
    if len(candles) < 20:
        return True, "INSUFFICIENT_DATA"
    
    recent_candles = candles[-20:]
    high_range = max(c.get('high', 0) for c in recent_candles)
    low_range = min(c.get('low', 0) for c in recent_candles)
    
    if high_range <= low_range:
        return True, "INVALID_RANGE"
    
    range_pos = (current_price - low_range) / (high_range - low_range)
    
    if signal_type == "BUY":
        if range_pos > 0.75:
            return False, "BUYING_AT_TOP"
        if range_pos < 0.25:
            return True, "OK"
    elif signal_type == "SELL":
        if range_pos < 0.25:
            return False, "SELLING_AT_BOTTOM"
        if range_pos > 0.75:
            return True, "OK"
    
    return True, "OK"


def get_regime_enforcement(regime: str, signal_type: str, is_reversal: bool) -> tuple:
    if regime == "LOW_VOL":
        return False, "LOW_VOL_REGIME"
    
    if regime == "TRENDING":
        if not is_reversal:
            return True, "CONTINUATION_OK"
        else:
            return False, "REVERSAL_IN_TRENDING"
    
    if regime == "RANGE" or regime == "TRANSITION":
        if is_reversal:
            return True, "REVERSAL_OK"
        else:
            return True, "CONTINUATION_OK"
    
    return True, "OK"


def calculate_weighted_confidence(
    trend_strength: float,
    volume_strength: float,
    liquidity_signal: float,
    whale_signal: float,
    entry_score: float,
    regime_alignment: float
) -> float:
    weights = WEIGHTED_WEIGHTS
    
    weighted_score = (
        weights["trend_strength"] * trend_strength +
        weights["volume_strength"] * volume_strength +
        weights["liquidity_signal"] * liquidity_signal +
        weights["whale_signal"] * whale_signal +
        weights["entry_score"] * entry_score +
        weights["regime_alignment"] * regime_alignment
    )
    
    return round(weighted_score, 2)


def normalize_to_100(raw_score: float) -> int:
    normalized = min(100, max(0, raw_score))
    return int(normalized)


def calculate_confidence_with_weights(
    trend_strength: float,
    volume_strength: float,
    liquidity_score: float,
    whale_score: float,
    entry_quality_score: float,
    regime_score: float
) -> int:
    confidence = calculate_weighted_confidence(
        trend_strength=trend_strength * 100,
        volume_strength=volume_strength * 100,
        liquidity_signal=liquidity_score,
        whale_signal=whale_score,
        entry_score=entry_quality_score,
        regime_alignment=regime_score * 100
    )
    
    return normalize_to_100(confidence)


FEATURE_STATS = {
    "liquidity": {"wins": 0, "losses": 0},
    "bos": {"wins": 0, "losses": 0},
    "choch": {"wins": 0, "losses": 0},
    "fvg": {"wins": 0, "losses": 0},
    "volume": {"wins": 0, "losses": 0},
    "whale": {"wins": 0, "losses": 0},
    "htf_aligned": {"wins": 0, "losses": 0},
    "vwap_aligned": {"wins": 0, "losses": 0},
    "reversal_strong": {"wins": 0, "losses": 0}
}

ADAPTIVE_WEIGHTS = {
    "liquidity": 20,
    "bos": 15,
    "choch": 20,
    "fvg": 5,
    "volume": 15,
    "whale": 15,
    "htf_aligned": 8,
    "vwap_aligned": 8,
    "reversal_strong": 20
}


def update_feature_stats(trade_result: str, features: Dict):
    if trade_result not in ["WIN", "LOSS"]:
        return
    
    for feature, active in features.items():
        if not active or feature not in FEATURE_STATS:
            continue
        
        if trade_result == "WIN":
            FEATURE_STATS[feature]["wins"] += 1
        else:
            FEATURE_STATS[feature]["losses"] += 1


def get_adaptive_weight(feature: str) -> int:
    if feature not in ADAPTIVE_WEIGHTS:
        return 10
    
    stats = FEATURE_STATS.get(feature, {"wins": 0, "losses": 0})
    total = stats["wins"] + stats["losses"]
    
    if total < 10:
        return ADAPTIVE_WEIGHTS.get(feature, 10)
    
    win_rate = stats["wins"] / total
    
    if win_rate > 0.6:
        return ADAPTIVE_WEIGHTS.get(feature, 10) + 5
    elif win_rate > 0.5:
        return ADAPTIVE_WEIGHTS.get(feature, 10)
    elif win_rate > 0.4:
        return max(5, ADAPTIVE_WEIGHTS.get(feature, 10) - 5)
    else:
        return max(3, ADAPTIVE_WEIGHTS.get(feature, 10) - 8)


def calculate_adaptive_confidence(signal: Dict) -> int:
    features = {
        "liquidity": signal.get("liquidity") is not None and "REJECTION" in str(signal.get("liquidity", "")),
        "bos": signal.get("bos") is not None,
        "choch": signal.get("choch") is not None,
        "fvg": signal.get("fvg") is not None,
        "volume": signal.get("volume", False),
        "whale": signal.get("whale_signal") != "NEUTRAL",
        "htf_aligned": "UPTREND" in signal.get("trend", "") or "DOWNTREND" in signal.get("trend", ""),
        "vwap_aligned": signal.get("vwap_bias") in ["BULLISH", "BEARISH"],
        "reversal_strong": signal.get("setup_type") == "REVERSAL_STRONG"
    }
    
    base_score = 40
    
    for feature, active in features.items():
        if active:
            base_score += get_adaptive_weight(feature)
    
    return min(100, max(0, base_score))


def get_feature_performance() -> Dict:
    performance = {}
    for feature, stats in FEATURE_STATS.items():
        total = stats["wins"] + stats["losses"]
        if total > 0:
            win_rate = stats["wins"] / total
            performance[feature] = {
                "wins": stats["wins"],
                "losses": stats["losses"],
                "total": total,
                "win_rate": round(win_rate * 100, 1)
            }
    return performance