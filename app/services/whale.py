from typing import List, Dict, Tuple, Optional
import config


def calculate_cvd(candles: List[Dict]) -> float:
    if not candles or len(candles) < 2:
        return 0.0
    
    cvd = 0.0
    for candle in candles[-20:]:
        close = candle['close']
        open_price = candle['open']
        volume = candle.get('volume', 1)
        
        if close > open_price:
            cvd += volume
        elif close < open_price:
            cvd -= volume
    
    return cvd


def detect_oi_spike(oi_data: List[float]) -> Tuple[bool, float]:
    if not oi_data or len(oi_data) < 10:
        return False, 0.0
    
    recent_oi = oi_data[-5:]
    older_oi = oi_data[-10:-5]
    
    if not older_oi or sum(older_oi) == 0:
        return False, 0.0
    
    recent_avg = sum(recent_oi) / len(recent_oi)
    older_avg = sum(older_oi) / len(older_oi)
    
    oi_spike_pct = (recent_avg - older_avg) / older_avg
    
    is_spike = oi_spike_pct > 0.05
    
    return is_spike, round(oi_spike_pct * 100, 2)


def detect_liquidation_cluster(candles: List[Dict]) -> Tuple[bool, float]:
    if not candles or len(candles) < 20:
        return False, 0.0
    
    recent = candles[-10:]
    current = candles[-1]
    
    wicks = [c['high'] - c['low'] for c in recent]
    avg_wick = sum(wicks) / len(wicks)
    
    current_wick = current['high'] - current['low']
    
    large_wick_ratio = current_wick / avg_wick if avg_wick > 0 else 1.0
    
    is_cluster = large_wick_ratio > 2.0
    
    return is_cluster, round(large_wick_ratio, 2)


def analyze_trend_strength(price_change: float, oi_change: float) -> Tuple[str, float]:
    if price_change > 0.005 and oi_change > 0.03:
        return "STRONG_BULL", 20
    elif price_change > 0.005 and oi_change < -0.03:
        return "WEAK_BULL", -10
    elif price_change < -0.005 and oi_change > 0.03:
        return "STRONG_BEAR", 20
    elif price_change < -0.005 and oi_change < -0.03:
        return "WEAK_BEAR", -10
    elif abs(price_change) < 0.001 and abs(oi_change) < 0.01:
        return "ACCUMULATION_ZONE", 10
    
    return "NEUTRAL", 0


def detect_oi_divergence(prices: List[float], oi_data: List[float]) -> Tuple[str, float]:
    if not prices or not oi_data or len(prices) < 5 or len(oi_data) < 5:
        return "UNKNOWN", 0
    
    price_change = get_price_trend(prices)
    oi_change = get_oi_trend(oi_data)
    
    if price_change > 0 and oi_change < -0.02:
        return "OI_DIV_BEARISH", -15
    elif price_change < 0 and oi_change < -0.02:
        return "LONG_LIQUIDATION_BULLISH", 10
    elif price_change < 0 and oi_change > 0.02:
        return "OI_DIV_BULLISH", 15
    elif price_change > 0 and oi_change > 0.02:
        return "SHORT_COVERING_BEARISH", -10
    
    return "ALIGNED", 0


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
    if not candles or len(candles) < 10:
        return "NEUTRAL", 0.0
    
    prices = [c["close"] for c in candles]
    
    price_change = get_price_trend(prices)
    oi_change = get_oi_trend(oi_data) if oi_data else 0.0
    
    is_oi_spike, oi_spike_pct = detect_oi_spike(oi_data) if oi_data else (False, 0.0)
    is_liquidation, liquidation_ratio = detect_liquidation_cluster(candles)
    cvd = calculate_cvd(candles)
    
    trend_type, trend_bonus = analyze_trend_strength(price_change, oi_change)
    
    if is_liquidation and price_change > 0:
        return "LIQUIDATION_BUY", 20
    elif is_liquidation and price_change < 0:
        return "LIQUIDATION_SELL", 20
    
    if price_change > 0.005 and oi_change > 0.03:
        return "ACCUMULATION", 15
    elif price_change < -0.005 and oi_change > 0.03:
        return "DISTRIBUTION", 15
    elif price_change > 0.005 and oi_change < -0.03:
        return "SHORT_SQUEEZE", 10
    elif price_change < -0.005 and oi_change < -0.03:
        return "LONG_LIQUIDATION", -10
    
    if cvd > 0 and price_change > 0:
        return "CVD_BULLISH", 10
    elif cvd < 0 and price_change < 0:
        return "CVD_BEARISH", 10
    
    return "NEUTRAL", trend_bonus


def get_whale_metrics(candles: List[Dict], oi_data: List[float]) -> Dict:
    if not candles or len(candles) < 10:
        return {"cvd": 0, "oi_spike": False, "liquidation_cluster": False, "trend_type": "UNKNOWN"}
    
    prices = [c["close"] for c in candles]
    cvd = calculate_cvd(candles)
    is_oi_spike, oi_spike_pct = detect_oi_spike(oi_data) if oi_data else (False, 0.0)
    is_liquidation, liquidation_ratio = detect_liquidation_cluster(candles)
    trend_type, _ = analyze_trend_strength(get_price_trend(prices), get_oi_trend(oi_data) if oi_data else 0)
    
    return {
        "cvd": round(cvd, 2),
        "oi_spike": is_oi_spike,
        "oi_spike_pct": oi_spike_pct,
        "liquidation_cluster": is_liquidation,
        "liquidation_ratio": liquidation_ratio,
        "trend_type": trend_type,
        "price_trend_pct": round(get_price_trend(prices) * 100, 2),
        "oi_trend_pct": round(get_oi_trend(oi_data) * 100, 2) if oi_data else 0
    }


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
