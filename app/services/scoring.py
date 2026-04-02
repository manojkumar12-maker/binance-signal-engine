from typing import Optional, Dict, List
import logging
import config

logger = logging.getLogger("scoring_debug")


def calculate_confidence(
    trend: str, 
    liquidity: Optional[str], 
    volume: bool, 
    strength: int = 0, 
    volume_spike: bool = False,
    htf_aligned: bool = True,
    market_bias: Optional[Dict] = None,
    is_reversal: bool = False,
    debug: bool = False
) -> int:
    score = 35
    reasons = []
    
    if trend != "RANGE":
        score += 12
    else:
        reasons.append("RANGE_TREND")
        score -= 15
    
    if htf_aligned:
        score += 8
    else:
        if liquidity and "REJECTION" in liquidity:
            score += 5
            reasons.append("HTF_MISMATCH_REVERSAL")
        else:
            score -= 12
            reasons.append("HTF_MISMATCH")
    
    if liquidity is not None:
        if "REJECTION" in liquidity:
            score += 12
        else:
            score += 8
    else:
        score -= 8
        reasons.append("NO_LIQUIDITY")
    
    if volume_spike:
        score += 12
    else:
        score += 2
    
    score += min(strength, 8)
    
    if is_reversal:
        score += 8
        reasons.append("REVERSAL")
    
    if not liquidity:
        score -= 20
    
    if market_bias:
        bias = market_bias.get("bias", "NEUTRAL")
        signal = "BUY" if trend == "UPTREND" else "SELL"
        
        if bias == "BULLISH" and signal == "BUY":
            score += 6
        elif bias == "BEARISH" and signal == "SELL":
            score += 6
        elif bias in ["BULLISH", "BEARISH"]:
            score -= 15
            reasons.append("BIAS_MISMATCH")
    
    score = max(0, min(score, 85))
    
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