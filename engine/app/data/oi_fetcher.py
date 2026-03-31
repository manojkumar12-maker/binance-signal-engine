import requests
import time
import logging
from app.core.config import BINANCE_FUTURES_URL, PAIRS, OI_FETCH_INTERVAL
from app.core.redis_client import set_data

logger = logging.getLogger(__name__)


def fetch_oi(symbol: str) -> float:
    try:
        url = f"{BINANCE_FUTURES_URL}/fapi/v1/openInterest?symbol={symbol}"
        response = requests.get(url, timeout=10)
        data = response.json()
        return float(data.get('openInterest', 0))
    except Exception as e:
        logger.error(f"Error fetching OI for {symbol}: {e}")
        return 0


def fetch_all_oi(pairs: list = None):
    pairs = pairs or PAIRS
    
    for pair in pairs:
        oi = fetch_oi(pair)
        if oi > 0:
            set_data(f"{pair}:oi", oi)
            logger.debug(f"Fetched OI for {pair}: {oi}")
        time.sleep(0.1)


def get_cached_oi(symbol: str) -> float:
    return get_data(f"{symbol}:oi") or 0


async def run_oi_fetcher():
    logger.info("Starting OI fetcher...")
    while True:
        try:
            fetch_all_oi()
        except Exception as e:
            logger.error(f"OI fetch error: {e}")
        await asyncio.sleep(OI_FETCH_INTERVAL)


import asyncio

if __name__ == "__main__":
    fetch_all_oi()
    print("OI fetched for all pairs")
