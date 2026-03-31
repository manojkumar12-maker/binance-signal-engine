import asyncio
import logging
import os
import sys
from datetime import datetime

current = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current)

from core.websocket_manager import stream
from core.scheduler import run_scanner, run_monitoring
from data.oi_fetcher import run_oi_fetcher

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


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
    logger.info(f"🚀 Starting all services...")
    logger.info(f"")
    
    try:
        await asyncio.gather(
            stream(),
            run_scanner(),
            run_monitoring(),
            run_oi_fetcher()
        )
    except KeyboardInterrupt:
        logger.info(f"")
        logger.info(f"⚠️ Shutting down...")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
