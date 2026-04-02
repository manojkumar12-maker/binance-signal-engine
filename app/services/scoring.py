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