import logging

logger = logging.getLogger(__name__)

def get_market_bias(candles_1h: list, candles_4h: list) -> dict:
    if not candles_1h or len(candles_1h) < 20:
        return {"bias": "NEUTRAL", "score": 0}
    
    recent_1h = candles_1h[-20:]
    
    highs = [c["high"] for c in recent_1h]
    lows = [c["low"] for c in recent_1h]
    closes = [c["close"] for c in recent_1h]
    
    hh = all(highs[i] > highs[i-1] for i in range(1, len(highs)))
    hl = all(lows[i] > lows[i-1] for i in range(1, len(lows)))
    
    lh = all(highs[i] < highs[i-1] for i in range(1, len(highs)))
    ll = all(lows[i] < lows[i-1] for i in range(1, len(lows)))
    
    if hh and hl:
        bias = "BULLISH"
        score = 70
    elif lh and ll:
        bias = "BEARISH"
        score = 70
    else:
        bias = "NEUTRAL"
        score = 30
    
    ma20 = sum(closes) / len(closes)
    current_price = closes[-1]
    
    if current_price > ma20 * 1.01:
        score += 15
    elif current_price < ma20 * 0.99:
        score -= 15
    
    return {"bias": bias, "score": max(0, min(100, score))}

def calculate_trend(candles: list) -> str:
    if not candles or len(candles) < 20:
        return "UNKNOWN"
    
    recent = candles[-20:]
    highs = [c["high"] for c in recent]
    lows = [c["low"] for c in recent]
    
    hh = all(highs[i] > highs[i-1] for i in range(1, len(highs)))
    hl = all(lows[i] > lows[i-1] for i in range(1, len(lows)))
    
    if hh and hl:
        return "UPTREND"
    
    lh = all(highs[i] < highs[i-1] for i in range(1, len(highs)))
    ll = all(lows[i] < lows[i-1] for i in range(1, len(lows)))
    
    if lh and ll:
        return "DOWNTREND"
    
    return "RANGE"