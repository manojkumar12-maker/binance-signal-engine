from typing import Optional, Dict, List


def calculate_confidence(
    trend: str, 
    liquidity: Optional[str], 
    volume: bool, 
    strength: int = 0, 
    volume_spike: bool = False,
    htf_aligned: bool = True,
    market_bias: Optional[Dict] = None,
    is_reversal: bool = False
) -> int:
    score = 0
    
    if trend != "RANGE":
        score += 20
    
    if htf_aligned:
        score += 15
    else:
        if liquidity and "REJECTION" in liquidity:
            score += 5
        else:
            score -= 10
    
    if liquidity is not None:
        if "REJECTION" in liquidity:
            score += 25
        else:
            score += 15
    
    if volume_spike:
        score += 20
    else:
        score += 5
    
    score += min(strength, 15)
    
    if is_reversal:
        score += 15
    
    if market_bias:
        bias = market_bias.get("bias", "NEUTRAL")
        signal = "BUY" if trend == "UPTREND" else "SELL"
        
        if bias == "BULLISH" and signal == "BUY":
            score += 10
        elif bias == "BEARISH" and signal == "SELL":
            score += 10
        elif bias in ["BULLISH", "BEARISH"]:
            score -= 10
    
    return max(0, min(score, 100))


def detect_reversal(candles: List[Dict], sweep_type: Optional[str]) -> bool:
    if not sweep_type or "REJECTION" not in sweep_type:
        return False
    
    if len(candles) < 2:
        return False
    
    last = candles[-1]
    prev = candles[-2]
    
    body = abs(last['close'] - last['open'])
    candle_range = last['high'] - last['low']
    
    if candle_range == 0:
        return False
    
    strong_rejection = body < candle_range * 0.3
    
    if sweep_type == "SWEEP_LOW_REJECTION":
        momentum_shift = last['close'] > prev['close']
    elif sweep_type == "SWEEP_HIGH_REJECTION":
        momentum_shift = last['close'] < prev['close']
    else:
        momentum_shift = False
    
    return strong_rejection and momentum_shift


def get_signal_quality(score: int) -> str:
    if score >= 65:
        return "STRONG"
    elif score >= 55:
        return "WEAK"
    else:
        return "SKIP"