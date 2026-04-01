import requests
import asyncio
import time
import logging
from core.config import BINANCE_FUTURES_URL, OI_FETCH_INTERVAL, PAIRS, OI_FETCH_LIMIT
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
        
        if response.status_code == 429:
            logger.warning(f"Rate limited on {symbol}, returning cached")
            cached = get_data(f"{symbol}:oi") or 0
            return cached
        
        data = response.json()
        return float(data.get('openInterest', 0))
    except Exception as e:
        cached = get_data(f"{symbol}:oi") or 0
        return cached


def get_active_pairs_for_oi(pairs: list, cache: dict, min_move_pct: float = 0.003) -> list:
    active = []
    
    for p in pairs:
        candles = cache.get(p)
        
        if not candles or len(candles) < 2:
            continue
        
        last = candles[-1]
        prev = candles[-2]
        
        prev_close = prev.get('close', 0)
        if prev_close == 0:
            continue
        
        move = abs(last.get('close', 0) - prev_close) / prev_close
        
        if move > min_move_pct:
            active.append(p)
    
    return active[:OI_FETCH_LIMIT]


def fetch_active_oi():
    pairs = get_active_pairs()
    if not pairs:
        pairs = PAIRS[:OI_FETCH_LIMIT]
    
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
    logger.info(f"   📌 Mode: Active pairs only (filtered by movement)")
    logger.info(f"   📌 Max pairs: {OI_FETCH_LIMIT}")
    
    while True:
        try:
            cache = {}
            for pair in PAIRS:
                candles = get_data(f"{pair}:1h")
                if candles:
                    cache[pair] = candles
            
            oi_pairs = get_active_pairs_for_oi(PAIRS, cache)
            logger.info(f"📊 Fetching OI for {len(oi_pairs)} active pairs...")
            
            fetched = 0
            for i, pair in enumerate(oi_pairs):
                if i > 0 and i % 10 == 0:
                    await asyncio.sleep(1)
                
                oi = fetch_oi(pair)
                if oi > 0:
                    set_data(f"{pair}:oi", oi)
                    fetched += 1
                
                await asyncio.sleep(0.05)
            
            logger.info(f"✅ OI refreshed: {fetched} pairs")
        except Exception as e:
            logger.error(f"❌ OI fetch error: {e}")
        
        await asyncio.sleep(OI_FETCH_INTERVAL)


if __name__ == "__main__":
    fetch_active_oi()
    print("OI fetched for active pairs")
