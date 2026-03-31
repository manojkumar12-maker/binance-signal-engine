import requests
import asyncio
import time
import logging
from core.config import BINANCE_FUTURES_URL, OI_FETCH_INTERVAL, PAIRS
from core.redis_client import set_data, get_data
from core.logging_utils import setup_logger

logger = setup_logger("oi_fetcher", logging.INFO)

ACTIVE_PAIRS = set()


def register_active_pair(pair: str):
    ACTIVE_PAIRS.add(pair)


def get_active_pairs() -> list:
    return list(ACTIVE_PAIRS)


def fetch_oi(symbol: str) -> float:
    try:
        url = f"{BINANCE_FUTURES_URL}/fapi/v1/openInterest?symbol={symbol}"
        response = requests.get(url, timeout=10)
        data = response.json()
        return float(data.get('openInterest', 0))
    except Exception as e:
        logger.error(f"Error fetching OI for {symbol}: {e}")
        return 0


def fetch_active_oi():
    pairs = get_active_pairs()
    if not pairs:
        pairs = PAIRS
    
    fetched = 0
    for pair in pairs:
        oi = fetch_oi(pair)
        if oi > 0:
            set_data(f"{pair}:oi", oi)
            fetched += 1
        time.sleep(0.05)
    
    return fetched


def get_cached_oi(symbol: str) -> float:
    return get_data(f"{symbol}:oi") or 0


async def run_oi_fetcher():
    logger.info(f"")
    logger.info(f"📊 OI (Open Interest) FETCHER STARTED")
    logger.info(f"   ⏱️ Fetch interval: {OI_FETCH_INTERVAL} seconds")
    logger.info(f"   📌 Mode: Active pairs only (lazy fetch)")
    
    while True:
        try:
            active = get_active_pairs()
            count = len(active) if active else len(PAIRS)
            logger.info(f"📊 Fetching OI for {count} active pairs...")
            
            fetched = fetch_active_oi()
            logger.info(f"✅ OI refreshed: {fetched} pairs")
        except Exception as e:
            logger.error(f"❌ OI fetch error: {e}")
        
        await asyncio.sleep(OI_FETCH_INTERVAL)


if __name__ == "__main__":
    fetch_active_oi()
    print("OI fetched for active pairs")
