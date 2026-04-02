from typing import List, Dict, Tuple, Optional


def get_oi_trend(oi_series: List[float]) -> float:
    if not oi_series or len(oi_series) < 5:
        return 0.0
    
    recent_oi = oi_series[-5:]
    oi_change = (recent_oi[-1] - recent_oi[0]) / recent_oi[0] if recent_oi[0] > 0 else 0
    
    return oi_change


def get_price_trend(prices: List[float]) -> float:
    if not prices or len(prices) < 5:
        return 0.0
    
    recent_prices = prices[-5:]
    price_change = (recent_prices[-1] - recent_prices[0]) / recent_prices[0] if recent_prices[0] > 0 else 0
    
    return price_change


def detect_whale_activity(candles: List[Dict], oi_data: List[float]) -> Tuple[str, float]:
    if not candles or len(candles) < 10 or not oi_data or len(oi_data) < 5:
        return "NEUTRAL", 0.0
    
    prices = [c["close"] for c in candles]
    
    price_change = get_price_trend(prices)
    oi_change = get_oi_trend(oi_data)
    
    if price_change > 0.005 and oi_change > 0.03:
        return "ACCUMULATION", 15
    elif price_change < -0.005 and oi_change > 0.03:
        return "DISTRIBUTION", 15
    elif price_change > 0.005 and oi_change < -0.03:
        return "SHORT_SQUEEZE", 10
    elif price_change < -0.005 and oi_change < -0.03:
        return "LONG_LIQUIDATION", -10
    
    return "NEUTRAL", 0


def get_volatility_regime(atr_ratio: float) -> Tuple[str, Dict]:
    if atr_ratio < 0.0008:
        return "DEAD", {"tp_mult": 1.0, "sl_mult": 1.2, "min_conf": 75}
    elif atr_ratio < 0.003:
        return "NORMAL", {"tp_mult": 1.5, "sl_mult": 1.5, "min_conf": 65}
    else:
        return "HIGH_VOL", {"tp_mult": 1.8, "sl_mult": 2.0, "min_conf": 60}


def order_flow_strength(candle: Dict) -> float:
    body = abs(candle['close'] - candle['open'])
    wick = candle['high'] - candle['low']
    
    if wick == 0:
        return 0.0
    
    return body / wick


def is_fake_breakout(candles: List[Dict]) -> bool:
    if len(candles) < 10:
        return False
    
    recent = candles[-10:-1]
    last = candles[-1]
    prev = candles[-2]
    
    highest_high = max(c["high"] for c in recent)
    
    breakout = last["high"] > highest_high
    
    rejection = last["close"] < prev["close"]
    
    low_vol = order_flow_strength(last) < 0.4
    
    return breakout and (rejection or low_vol)


def validate_liquidity_zone(sweep: Optional[str], candle: Dict, prev_candle: Dict) -> bool:
    if not sweep:
        return False
    
    if "SWEEP_LOW" in sweep:
        return candle["close"] > prev_candle["low"]
    elif "SWEEP_HIGH" in sweep:
        return candle["close"] < prev_candle["high"]
    
    return False


def calculate_whale_bonus(whale_signal: str, trade_signal: str) -> int:
    if whale_signal == "ACCUMULATION" and trade_signal == "BUY":
        return 15
    elif whale_signal == "DISTRIBUTION" and trade_signal == "SELL":
        return 15
    elif whale_signal == "SHORT_SQUEEZE" and trade_signal == "BUY":
        return 10
    elif whale_signal == "LONG_LIQUIDATION" and trade_signal == "SELL":
        return 10
    elif whale_signal in ["ACCUMULATION", "DISTRIBUTION", "SHORT_SQUEEZE", "LONG_LIQUIDATION"]:
        return -15
    
    return 0
