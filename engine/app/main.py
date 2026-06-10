import asyncio
import logging
import os
import sys
import signal
from datetime import datetime

current = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current)

LOCK_FILE = os.environ.get("LOCK_FILE", "/tmp/binance_signal_engine.lock")

def acquire_lock():
    try:
        if os.path.exists(LOCK_FILE):
            try:
                with open(LOCK_FILE, 'r') as f:
                    old_pid = f.read().strip()
                if old_pid and old_pid.isdigit():
                    try:
                        os.kill(int(old_pid), 0)
                        print(f"FATAL: Process {old_pid} is already running. Exiting...")
                        sys.exit(1)
                    except (ProcessLookupError, ValueError, PermissionError):
                        pass
            except:
                pass
        
        with open(LOCK_FILE, 'w') as f:
            f.write(str(os.getpid()))
        
        def cleanup(signum, frame):
            try:
                os.remove(LOCK_FILE)
            except:
                pass
            sys.exit(0)
        
        signal.signal(signal.SIGTERM, cleanup)
        signal.signal(signal.SIGINT, cleanup)
        
        return True
    except Exception as e:
        print(f"WARNING: Lock check failed: {e}")
        return True

if not acquire_lock():
    print("Failed to acquire lock, exiting...")
    sys.exit(1)

from core.scheduler import run_scanner, run_monitoring
from data.oi_fetcher import run_oi_fetcher
from core.logging_utils import setup_logger
from core.config import ENABLE_WS_FOR_TOP_PAIRS, TOP_PAIRS_COUNT

logger = setup_logger("main", logging.INFO)

LOG_PRINTED = False

def print_banner():
    global LOG_PRINTED
    if LOG_PRINTED:
        return
    LOG_PRINTED = True
    
    banner = """
╔═══════════════════════════════════════════════════════════════╗
║           ⚡ BINANCE SIGNAL ENGINE - RUNNING ⚡                 ║
╚═══════════════════════════════════════════════════════════════╝
"""
    logger.info(banner)


async def main():
    print_banner()
    
    start_time = datetime.now()
    
    logger.info("=== SYSTEM INITIALIZATION ===")
    logger.info(f"Started: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Mode: REST polling")
    logger.info("")
    
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
