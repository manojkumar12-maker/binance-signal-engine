import asyncio
import json
import logging
import websockets
from app.core.config import MAX_PAIRS_PER_STREAM, TIMEFRAMES, MAX_CANDLES
from app.core.config import PAIRS, chunk_pairs
from app.core.redis_client import get_data, set_data

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def build_stream_url(pairs_chunk, timeframe="1h"):
    streams = [f"{p.lower()}@kline_{timeframe}" for p in pairs_chunk]
    return f"wss://fstream.binance.com/stream?streams={'/'.join(streams)}"


async def handle_stream(pairs_chunk, timeframe="1h"):
    url = build_stream_url(pairs_chunk, timeframe)
    
    while True:
        try:
            async with websockets.connect(url, ping_interval=20, ping_timeout=10) as ws:
                logger.info(f"Connected: {len(pairs_chunk)} pairs - {timeframe}")
                
                while True:
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=30)
                        data = json.loads(msg)
                        if 'data' in data:
                            process_kline(data['data'])
                    except asyncio.TimeoutError:
                        continue
                    except Exception as e:
                        logger.error(f"Stream error: {e}")
                        break
        except Exception as e:
            logger.error(f"Reconnecting {len(pairs_chunk)} pairs: {e}")
            await asyncio.sleep(5)


def process_kline(data):
    kline = data['k']
    symbol = kline['s']
    timeframe = kline['i']
    is_closed = kline['x']
    
    candle = {
        "open": float(kline['o']),
        "high": float(kline['h']),
        "low": float(kline['l']),
        "close": float(kline['c']),
        "volume": float(kline['v']),
        "timestamp": kline['t'],
        "closed": is_closed
    }
    
    key = f"{symbol}:{timeframe}"
    candles = get_data(key) or []
    candles.append(candle)
    candles = candles[-MAX_CANDLES:]
    
    set_data(key, candles)


async def start_all_streams():
    logger.info(f"Starting streams for {len(PAIRS)} pairs...")
    
    pairs_1h = PAIRS
    pairs_4h = PAIRS
    
    chunks_1h = list(chunk_pairs(pairs_1h, MAX_PAIRS_PER_STREAM))
    chunks_4h = list(chunk_pairs(pairs_4h, MAX_PAIRS_PER_STREAM))
    
    logger.info(f"Created {len(chunks_1h)} chunks for 1H")
    logger.info(f"Created {len(chunks_4h)} chunks for 4H")
    
    tasks = []
    
    for i, chunk in enumerate(chunks_1h):
        tasks.append(asyncio.create_task(handle_stream(chunk, "1h")))
        await asyncio.sleep(0.5)
    
    for i, chunk in enumerate(chunks_4h):
        tasks.append(asyncio.create_task(handle_stream(chunk, "4h")))
        await asyncio.sleep(0.5)
    
    await asyncio.gather(*tasks)


async def stream():
    logger.info("Starting WebSocket stream...")
    await start_all_streams()


if __name__ == "__main__":
    asyncio.run(stream())
