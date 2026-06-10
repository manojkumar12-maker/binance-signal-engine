import config
from typing import Dict, List, Tuple, Optional
import requests
import time


CORRELATION_THRESHOLD = 0.7


ASSET_CATEGORIES = {
    "BTC": ["BTCUSDT"],
    "ETH": ["ETHUSDT"],
    "ALT": ["SOLUSDT", "XRPUSDT", "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "DOTUSDT"],
    "AI": ["FETUSDT", "RNDRUSDT", "OCEANUSDT"],
    "MEME": ["PEPEUSDT", "WIFUSDT", "BONKUSDT"],
    "DEFI": ["UNIUSDT", "AAVEUSDT", "MKRUSDT"]
}


def get_asset_category(symbol: str) -> str:
    for category, assets in ASSET_CATEGORIES.items():
        if symbol in assets:
            return category
    return "OTHER"


def get_price_history(symbol: str, interval: str = "1h", limit: int = 100) -> List[float]:
    try:
        url = f"{config.FUTURES_API_URL}/fapi/v1/klines"
        params = {"symbol": symbol, "interval": interval, "limit": limit}
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        return [float(candle[4]) for candle in data]
    except:
        return []


def calculate_correlation(prices1: List[float], prices2: List[float]) -> float:
    if not prices1 or not prices2:
        return 0.0
    
    min_len = min(len(prices1), len(prices2))
    p1 = prices1[-min_len:]
    p2 = prices2[-min_len:]
    
    if len(p1) < 10:
        return 0.0
    
    n = len(p1)
    mean1 = sum(p1) / n
    mean2 = sum(p2) / n
    
    num = sum((p1[i] - mean1) * (p2[i] - mean2) for i in range(n))
    den1 = sum((p1[i] - mean1) ** 2 for i in range(n)) ** 0.5
    den2 = sum((p2[i] - mean2) ** 2 for i in range(n)) ** 0.5
    
    if den1 == 0 or den2 == 0:
        return 0.0
    
    return num / (den1 * den2)


def check_correlation_with_open_trades(symbol: str, open_trades: List[Dict]) -> Tuple[bool, str]:
    if not open_trades:
        return True, "NO_OPEN_TRADES"
    
    symbol_category = get_asset_category(symbol)
    
    category_count = sum(
        1 for t in open_trades 
        if get_asset_category(t.get("pair", "")) == symbol_category
    )
    
    if category_count >= 2:
        return False, f"CATEGORY_LIMIT ({symbol_category}: {category_count} positions)"
    
    new_prices = get_price_history(symbol)
    if not new_prices:
        return True, "NO_PRICE_DATA"
    
    for trade in open_trades:
        if trade.get("pair") == symbol:
            continue
        
        existing_prices = get_price_history(trade.get("pair"))
        if not existing_prices:
            continue
        
        correlation = calculate_correlation(new_prices, existing_prices)
        
        if abs(correlation) > CORRELATION_THRESHOLD:
            return False, f"HIGH_CORRELATION ({trade.get('pair')}: {correlation:.2f})"
    
    return True, "OK"


def calculate_portfolio_exposure(open_trades: List[Dict]) -> Dict:
    exposure = {
        "total_value": 0,
        "long_value": 0,
        "short_value": 0,
        "by_category": {}
    }
    
    for trade in open_trades:
        pair = trade.get("pair", "")
        category = get_asset_category(pair)
        
        size = trade.get("position_size", trade.get("size", 0))
        
        exposure["total_value"] += size
        
        if trade.get("type") == "BUY":
            exposure["long_value"] += size
        else:
            exposure["short_value"] += size
        
        if category not in exposure["by_category"]:
            exposure["by_category"][category] = 0
        exposure["by_category"][category] += size
    
    return exposure


def should_reduce_size(symbol: str, open_trades: List[Dict]) -> Tuple[bool, str]:
    is_correlated, reason = check_correlation_with_open_trades(symbol, open_trades)
    
    if not is_correlated:
        return True, reason
    
    return False, "OK"


def validate_new_trade(symbol: str, open_trades: List[Dict], max_per_category: int = 2) -> Tuple[bool, str]:
    is_correlated, reason = check_correlation_with_open_trades(symbol, open_trades)
    if not is_correlated:
        return False, reason
    
    exposure = calculate_portfolio_exposure(open_trades)
    category = get_asset_category(symbol)
    
    category_exposure = exposure["by_category"].get(category, 0)
    if category_exposure >= max_per_category:
        return False, f"CATEGORY_EXPOSURE_LIMIT ({category}: {category_exposure})"
    
    return True, "OK"
