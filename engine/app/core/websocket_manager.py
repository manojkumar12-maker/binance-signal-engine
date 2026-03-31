import asyncio
import json
import logging
import websockets
from core.config import MAX_PAIRS_PER_STREAM, TIMEFRAMES, MAX_CANDLES
from core.config import PAIRS, chunk_pairs
from core.redis_client import get_data, set_data

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

WS_CONNECTIONS = 0
MESSAGES_RECEIVED = 0


def build_stream_url(pairs_chunk, timeframe="1h"):
    streams = [f"{p.lower()}@kline_{timeframe}" for p in pairs_chunk]
    return f"wss://fstream.binance.com/stream?streams={'/'.join(streams)}"


async def handle_stream(pairs_chunk, timeframe="1h"):
    global WS_CONNECTIONS, MESSAGES_RECEIVED
    
    url = build_stream_url(pairs_chunk, timeframe)
    
    while True:
        try:
            async with websockets.connect(url, ping_interval=20, ping_timeout=10) as ws:
                WS_CONNECTIONS += 1
                conn_id = WS_CONNECTIONS
                
                logger.info(f"")
                logger.info(f"🔌 WebSocket #{conn_id} CONNECTED")
                logger.info(f"   📊 Pairs: {len(pairs_chunk)}")
                logger.info(f"   ⏱️ Timeframe: {timeframe}")
                logger.info(f"   🌐 URL: {url[:60]}...")
                
                while True:
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=30)
                        MESSAGES_RECEIVED += 1
                        data = json.loads(msg)
                        if 'data' in data:
                            process_kline(data['data'])
                    except asyncio.TimeoutError:
                        continue
                    except Exception as e:
                        logger.error(f"Stream error #{conn_id}: {e}")
                        break
                        
        except Exception as e:
            logger.warning(f"⚠️ Reconnecting WebSocket ({len(pairs_chunk)} pairs {timeframe}): {e}")
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
    global WS_CONNECTIONS
    
    logger.info(f"")
    logger.info(f"╔" + "═" * 58 + "╗")
    logger.info(f"║" + " " * 10 + "WEBSOCKET MANAGER STARTING" + " " * 13 + "║")
    logger.info(f"╚" + "═" * 58 + "╝")
    
    logger.info(f"")
    logger.info(f"📊 Total pairs to monitor: {len(PAIRS)}")
    logger.info(f"🔢 Pairs per WebSocket: {MAX_PAIRS_PER_STREAM}")
    logger.info(f"⏱️ Timeframes: {TIMEFRAMES} (4H built internally)")
    
    pairs_1h = PAIRS
    
    chunks_1h = list(chunk_pairs(pairs_1h, MAX_PAIRS_PER_STREAM))
    
    logger.info(f"")
    logger.info(f"📦 WebSocket chunks:")
    logger.info(f"   • 1H: {len(chunks_1h)} chunks (optimized)")
    logger.info(f"   • Total: {len(chunks_1h)} connections (efficient)")
    
    logger.info(f"")
    logger.info(f"🚀 Starting WebSocket connections...")
    logger.info(f"=" * 50)
    
    tasks = []
    
    for i, chunk in enumerate(chunks_1h):
        tasks.append(asyncio.create_task(handle_stream(chunk, "1h")))
        logger.info(f"   📡 Queued chunk {i+1}/{len(chunks_1h)} ({len(chunk)} pairs)")
        await asyncio.sleep(0.3)
    
    logger.info(f"")
    logger.info(f"✅ All {len(tasks)} WebSocket connections started!")
    logger.info(f"=" * 50)
    
    await asyncio.gather(*tasks)


async def stream():
    logger.info("Starting WebSocket stream...")
    await start_all_streams()


if __name__ == "__main__":
    asyncio.run(stream())
