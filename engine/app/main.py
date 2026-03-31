import asyncio
import logging
import os
import sys

app_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, app_dir)

from app.core.websocket_manager import stream
from app.core.scheduler import run_scanner, run_monitoring
from app.data.oi_fetcher import run_oi_fetcher

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    logger.info("Starting Binance Signal Engine...")
    
    await asyncio.gather(
        stream(),
        run_scanner(),
        run_monitoring(),
        run_oi_fetcher()
    )


if __name__ == "__main__":
    asyncio.run(main())
