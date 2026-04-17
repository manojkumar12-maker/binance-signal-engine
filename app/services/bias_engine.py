from typing import Dict, List, Optional


def detect_trend(candles: List[Dict]) -> str:
    if len(candles) < 5:
        return "RANGE"
    
    recent = candles[-5:]
    highs = [c['high'] for c in recent]
    lows = [c['low'] for c in recent]
    
    if all(highs[i] > highs[i-1] for i in range(1, len(highs))) and \
       all(lows[i] > lows[i-1] for i in range(1, len(lows))):
        return "UPTREND"
    
    if all(highs[i] < highs[i-1] for i in range(1, len(highs))) and \
       all(lows[i] < lows[i-1] for i in range(1, len(lows))):
        return "DOWNTREND"
    
    return "RANGE"


def calculate_momentum(candles: List[Dict]) -> str:
    if len(candles) < 5:
        return "NEUTRAL"
    
    last_close = candles[-1]['close']
    prev_close = candles[-5]['close']
    
    change = (last_close - prev_close) / prev_close
    
    if change > 0.03:
        return "STRONG_BULL"
    elif change > 0.01:
        return "BULL"
    elif change < -0.03:
        return "STRONG_BEAR"
    elif change < -0.01:
        return "BEAR"
    else:
        return "NEUTRAL"


def calculate_atr(candles: List[Dict], period: int = 14) -> float:
    if len(candles) < period + 1:
        return 0.0
    
    trs = []
    for i in range(1, len(candles)):
        high = candles[i]['high']
        low = candles[i]['low']
        prev_close = candles[i-1]['close']
        
        tr = max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close)
        )
        trs.append(tr)
    
    return sum(trs[-period:]) / period


def get_market_bias(btc_1h: List[Dict], btc_4h: List[Dict]) -> Dict:
    if not btc_1h or len(btc_1h) < 5:
        return {
            "bias": "NEUTRAL",
            "score": 0,
            "reason": "INSUFFICIENT_DATA"
        }
    
    trend_ltf = detect_trend(btc_1h)
    trend_htf = detect_trend(btc_4h) if btc_4h and len(btc_4h) >= 5 else "RANGE"
    momentum = calculate_momentum(btc_1h)
    atr = calculate_atr(btc_1h)
    price = btc_1h[-1]['close']
    
    volatility = atr / price if price > 0 else 0
    
    score = 0
    
    if trend_ltf == "UPTREND" and trend_htf == "UPTREND":
        score += 40
    elif trend_ltf == "DOWNTREND" and trend_htf == "DOWNTREND":
        score -= 40
    elif trend_ltf == trend_htf and trend_ltf != "RANGE":
        score += 20 if trend_ltf == "UPTREND" else -20
    
    if momentum == "STRONG_BULL":
        score += 30
    elif momentum == "BULL":
        score += 15
    elif momentum == "STRONG_BEAR":
        score -= 30
    elif momentum == "BEAR":
        score -= 15
    
    if volatility < 0.002:
        return {
            "bias": "NEUTRAL",
            "score": 0,
            "trend_ltf": trend_ltf,
            "trend_htf": trend_htf,
            "momentum": momentum,
            "volatility": round(volatility, 4),
            "reason": "LOW_VOLATILITY"
        }
    
    if score >= 40:
        bias = "BULLISH"
    elif score <= -40:
        bias = "BEARISH"
    else:
        bias = "NEUTRAL"
    
    return {
        "bias": bias,
        "score": score,
        "trend_ltf": trend_ltf,
        "trend_htf": trend_htf,
        "momentum": momentum,
        "volatility": round(volatility, 4),
        "reason": None
    }


def apply_bias_filter(signal: str, market_bias: Dict) -> tuple[bool, Optional[str]]:
    if market_bias.get("reason") == "LOW_VOLATILITY":
        return False, "LOW_VOLATILITY"
    
    bias = market_bias.get("bias", "NEUTRAL")
    score = market_bias.get("score", 0)
    
    if bias == "BULLISH" and signal == "SELL":
        return False, "BIAS_MISMATCH_SELL"
    
    if bias == "BEARISH" and signal == "BUY":
        return False, "BIAS_MISMATCH_BUY"
    
    return True, None


def apply_bias_soft_penalty(confidence: int, signal: str, market_bias: Dict) -> int:
    if not market_bias:
        return confidence
    
    bias = market_bias.get("bias", "NEUTRAL")
    
    if bias == "BULLISH" and signal == "SELL":
        return max(0, confidence - 10)
    
    if bias == "BEARISH" and signal == "BUY":
        return max(0, confidence - 10)
    
    if bias == "BULLISH" and signal == "BUY":
        return confidence + 10
    
    if bias == "BEARISH" and signal == "SELL":
        return confidence + 10
    
    return confidence