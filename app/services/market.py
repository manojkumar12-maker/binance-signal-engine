import requests
import config
import logging

logger = logging.getLogger(__name__)

def get_klines(symbol: str, interval: str, limit: int = 100) -> list:
    try:
        url = f"{config.FUTURES_API_URL}/fapi/v1/klines"
        params = {"symbol": symbol, "interval": interval, "limit": limit}
        response = requests.get(url, params=params, timeout=10)
        return response.json()
    except Exception as e:
        logger.error(f"Error fetching klines for {symbol}: {e}")
        return []

def get_open_interest(symbol: str) -> dict:
    try:
        url = f"{config.FUTURES_API_URL}/fapi/v1/openInterest"
        params = {"symbol": symbol}
        response = requests.get(url, params=params, timeout=10)
        return response.json()
    except Exception as e:
        logger.error(f"Error fetching OI for {symbol}: {e}")
        return {}

def parse_klines(klines: list) -> list:
    candles = []
    for k in klines:
        candles.append({
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5]),
            "close_time": k[6]
        })
    return candles

def get_current_price(symbol: str) -> float:
    try:
        url = f"{config.FUTURES_API_URL}/fapi/v1/ticker/price"
        params = {"symbol": symbol}
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        return float(data.get("price", 0))
    except Exception as e:
        logger.error(f"Error fetching price for {symbol}: {e}")
        return 0

def get_24hr_stats(symbol: str) -> dict:
    try:
        url = f"{config.FUTURES_API_URL}/fapi/v1/ticker/24hr"
        params = {"symbol": symbol}
        response = requests.get(url, params=params, timeout=10)
        return response.json()
    except Exception as e:
        logger.error(f"Error fetching 24hr stats for {symbol}: {e}")
        return {}