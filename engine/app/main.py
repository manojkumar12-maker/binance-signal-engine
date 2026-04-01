import asyncio
import logging
import os
import sys
from datetime import datetime

current = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current)

from core.scheduler import run_scanner, run_monitoring
from data.oi_fetcher import run_oi_fetcher
from core.logging_utils import setup_logger
from core.config import ENABLE_WS_FOR_TOP_PAIRS, TOP_PAIRS_COUNT

logger = setup_logger("main", logging.INFO)


def print_banner():
    banner = f"""
╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║   ██████╗ ███████╗███████╗██╗     ██╗███╗   ██╗██████╗ ███████╗ ║
║   ██╔══██╗██╔════╝██╔════╝██║     ██║████╗  ██║██╔══██╗██╔════╝ ║
║   ██████╔╝█████╗  █████╗  ██║     ██║██╔██╗ ██║██████╔╝█████╗   ║
║   ██╔══██╗██╔══╝  ██╔══╝  ██║     ██║██║╚██╗██║██╔══██╗██╔══╝   ║
║   ██║  ██║███████╗███████╗███████╗██║██║ ╚████║██║  ██║███████╗ ║
║   ╚═╝  ╚═╝╚══════╝╚══════╝╚══════╝╚═╝╚═╝  ╚═══╝╚═╝  ╚═╝╚══════╝ ║
║                                                               ║
║              ██████╗ ██████╗ ███╗   ██╗███████╗ ██████╗ ███╗  ██╗║
║              ██╔══██╗██╔══██╗████╗  ██║██╔════╝██╔═══██╗████╗ ██║║
║              ██████╔╝██████╔╝██╔██╗ ██║█████╗  ██║   ██║██╔██╗██║║
║              ██╔══██╗██╔══██╗██║╚██╗██║██╔══╝  ██║   ██║██║╚████║║
║              ██████╔╝██║  ██║██║ ╚████║██║     ╚██████╔╝██║ ╚███║║
║              ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═══╝╚═╝      ╚═════╝ ╚═╝  ╚══╝║
║                                                               ║
║                  ⚡ SCALABLE SIGNAL ENGINE ⚡                  ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝
"""
    logger.info(banner)


async def main():
    print_banner()
    
    start_time = datetime.now()
    
    logger.info(f"")
    logger.info(f"╔" + "═" * 58 + "╗")
    logger.info(f"║" + " " * 15 + "SYSTEM INITIALIZATION" + " " * 20 + "║")
    logger.info(f"╚" + "═" * 58 + "╝")
    logger.info(f"")
    logger.info(f"⏰ Started at: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"📍 Working Directory: {current}")
    logger.info(f"")
    logger.info(f"🚀 Starting services (REST polling mode)...")
    logger.info(f"")
    
    tasks = [
        run_scanner(),
        run_monitoring(),
        run_oi_fetcher()
    ]
    
    if ENABLE_WS_FOR_TOP_PAIRS:
        from core.websocket_manager import stream_top_pairs
        logger.info(f"📡 Adding WebSocket for top {TOP_PAIRS_COUNT} pairs (optional)")
        tasks.append(stream_top_pairs())
    
    try:
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        logger.info(f"")
        logger.info(f"⚠️ Shutting down...")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
