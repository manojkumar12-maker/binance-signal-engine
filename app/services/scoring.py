from typing import Optional, Dict, List
import logging

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
    score = 50
    reasons = []
    
    if trend != "RANGE":
        score += 20
    else:
        reasons.append("RANGE_TREND")
        score -= 5
    
    if htf_aligned:
        score += 15
    else:
        if liquidity and "REJECTION" in liquidity:
            score += 5
            reasons.append("HTF_MISMATCH_REVERSAL")
        else:
            score -= 5
            reasons.append("HTF_MISMATCH")
    
    if liquidity is not None:
        if "REJECTION" in liquidity:
            score += 25
        else:
            score += 15
    else:
        score -= 5
        reasons.append("NO_LIQUIDITY")
    
    if volume_spike:
        score += 20
    else:
        score += 5
    
    score += min(strength, 15)
    
    if is_reversal:
        score += 15
        reasons.append("REVERSAL")
    
    if market_bias:
        bias = market_bias.get("bias", "NEUTRAL")
        signal = "BUY" if trend == "UPTREND" else "SELL"
        
        if bias == "BULLISH" and signal == "BUY":
            score += 10
        elif bias == "BEARISH" and signal == "SELL":
            score += 10
        elif bias in ["BULLISH", "BEARISH"]:
            score -= 5
            reasons.append("BIAS_MISMATCH")
    
    if debug:
        logger.info(f"SCORE={score} | REASONS={reasons}")
    
    return max(0, min(score, 100))


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


def get_signal_quality(score: int) -> str:
    if score >= 65:
        return "STRONG"
    elif score >= 50:
        return "WEAK"
    else:
        return "SKIP"