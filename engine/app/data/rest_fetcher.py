import asyncio
import aiohttp
import logging
from typing import List, Dict, Optional
from core.config import BINANCE_FUTURES_URL, MAX_CANDLES, TIMEFRAMES
from core.redis_client import get_data, set_data

logger = logging.getLogger("rest_fetcher")


async def fetch_candles_async(session: aiohttp.ClientSession, symbol: str, interval: str, limit: int = MAX_CANDLES) -> Optional[List[Dict]]:
    url = f"{BINANCE_FUTURES_URL}/fapi/v1/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    
    try:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                logger.warning(f"HTTP {resp.status} for {symbol}")
                return None
            
            data = await resp.json()
            
            candles = []
            for kline in data:
                candles.append({
                    "open": float(kline[1]),
                    "high": float(kline[2]),
                    "low": float(kline[3]),
                    "close": float(kline[4]),
                    "volume": float(kline[5]),
                    "timestamp": kline[0],
                    "closed": kline[0] < kline[6] if len(kline) > 6 else False
                })
            
            return candles
            
    except asyncio.TimeoutError:
        logger.warning(f"Timeout fetching {symbol}")
        return None
    except Exception as e:
        logger.warning(f"Error {symbol}: {e}")
        return None


async def fetch_oi_async(session: aiohttp.ClientSession, symbol: str) -> Optional[Dict]:
    url = f"{BINANCE_FUTURES_URL}/fapi/v1/openInterest"
    params = {"symbol": symbol}
    
    try:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=5)) as resp:
            if resp.status != 200:
                return None
            
            data = await resp.json()
            return {
                "open_interest": float(data.get("openInterest", 0)),
                "timestamp": data.get("timestamp", 0)
            }
            
    except Exception as e:
        return None


async def fetch_top_pairs_async(session: aiohttp.ClientSession, limit: int = 50) -> List[str]:
    url = f"{BINANCE_FUTURES_URL}/fapi/v1/ticker/24hr"
    
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                return []
            
            data = await resp.json()
            
            usdt_pairs = [t for t in data if t.get("quoteAsset") == "USDT" and t.get("contractType") == "PERPETUAL"]
            usdt_pairs.sort(key=lambda x: float(x.get("quoteVolume", 0)), reverse=True)
            
            return [t["symbol"] for t in usdt_pairs[:limit]]
            
    except Exception as e:
        logger.warning(f"Error fetching top pairs: {e}")
        return []


async def fetch_all_candles(pairs: List[str], timeframe: str = "1h") -> int:
    updated = 0
    
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_candles_async(session, p, timeframe) for p in pairs]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for pair, candles in zip(pairs, results):
            if isinstance(candles, list) and candles:
                key = f"{pair}:{timeframe}"
                set_data(key, candles)
                updated += 1
    
    return updated


async def fetch_all_oi(pairs: List[str]) -> int:
    updated = 0
    
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_oi_async(session, p) for p in pairs]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for pair, oi_data in zip(pairs, results):
            if isinstance(oi_data, dict) and oi_data.get("open_interest", 0) > 0:
                oi = oi_data["open_interest"]
                set_data(f"{pair}:oi", oi)
                
                history = get_data(f"{pair}:oi_history") or []
                history.append(oi)
                history = history[-20:]
                set_data(f"{pair}:oi_history", history)
                
                updated += 1
    
    return updated


async def sync_all_data(pairs: List[str], timeframe: str = "1h") -> Dict:
    logger.info(f"Syncing data for {len(pairs)} pairs...")
    
    candles_updated = await fetch_all_candles(pairs, timeframe)
    oi_updated = await fetch_all_oi(pairs)
    
    logger.info(f"Updated: {candles_updated} candles, {oi_updated} OI")
    
    return {
        "candles_updated": candles_updated,
        "oi_updated": oi_updated,
        "pairs": len(pairs)
    }


async def quick_update(pairs: List[str]) -> int:
    return await fetch_all_candles(pairs, "1h")
