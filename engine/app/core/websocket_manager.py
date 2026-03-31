import asyncio
import json
import logging
import websockets
from datetime import datetime
from app.core.config import BINANCE_WS_URL, PAIRS, TIMEFRAMES, MAX_CANDLES
from app.core.redis_client import get_data, set_data

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def build_streams():
    streams = []
    for pair in PAIRS:
        for tf in TIMEFRAMES:
            streams.append(f"{pair.lower()}@kline_{tf}")
    return "/".join(streams)


async def connect_websocket():
    url = f"{BINANCE_WS_URL}?streams={build_streams()}"
    
    while True:
        try:
            async with websockets.connect(url, ping_timeout=30) as ws:
                logger.info("WebSocket connected")
                
                while True:
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=30)
                        data = json.loads(msg)
                        if 'data' in data:
                            process_kline(data['data'])
                    except asyncio.TimeoutError:
                        continue
                    except Exception as e:
                        logger.error(f"Error processing: {e}")
                        break
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
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
    
    if is_closed:
        logger.info(f"Closed candle: {symbol} {timeframe}")


async def stream():
    logger.info("Starting WebSocket stream...")
    await connect_websocket()


if __name__ == "__main__":
    asyncio.run(stream())
