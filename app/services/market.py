import requests
from typing import List, Dict, Optional
import app.config as config


def get_klines(symbol: str, interval: str = "1h", limit: int = 100) -> List[Dict]:
    url = f"{config.BINANCE_API_URL}/api/v3/klines"
    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        candles = []
        for kline in data:
            candles.append({
                "open_time": kline[0],
                "open": float(kline[1]),
                "high": float(kline[2]),
                "low": float(kline[3]),
                "close": float(kline[4]),
                "volume": float(kline[5]),
                "close_time": kline[6]
            })
        return candles
    except Exception as e:
        return []


def get_current_price(symbol: str) -> Optional[float]:
    url = f"{config.BINANCE_API_URL}/api/v3/ticker/price"
    params = {"symbol": symbol}
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        return float(data["price"])
    except Exception:
        return None


def get_open_interest(symbol: str) -> List[float]:
    url = f"{config.FUTURES_API_URL}/fapi/v3/openInterest"
    params = {"symbol": symbol}
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        return [float(data.get("openInterest", 0))]
    except Exception:
        return []
