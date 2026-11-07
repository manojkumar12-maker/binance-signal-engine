"""Main worker loop: monitor -> signal -> risk -> execute (demo by default)."""
import time
import logging
import json
from decimal import Decimal
from .config import settings
from .binance_client import BinanceClient
from .signal_engine import SignalEngine
from .scanner import Scanner
from .orchestrator import Orchestrator
from .execution import ExecutionEngine
from .storage import Storage
from .kill_switch import KillSwitch
from .worker_lock import WorkerLock
from .reconciliation import ReconciliationService
from .market_data import MarketDataService

logging.basicConfig(level=getattr(logging, settings.log_level, logging.INFO))
log = logging.getLogger("worker")

INTERVAL_MS = {"1m": 60000, "3m": 180000, "5m": 300000, "15m": 900000, "30m": 1800000, "1h": 3600000}


def build_client() -> BinanceClient:
    key, secret = settings.credentials
    testnet = settings.use_testnet or settings.trading_mode != "live"
    c = BinanceClient(api_key=key, api_secret=secret, testnet=testnet)
    try:
        c.sync_time()
    except Exception as e:
        log.warning("time sync failed: %s", e)
    return c


def validate_candles(kl: list) -> tuple[bool, str]:
    if not kl or len(kl) < 50:
        return False, "insufficient candles"
    times = [k[0] for k in kl]
    if times != sorted(times):
        return False, "candles out of order"
    interval = INTERVAL_MS.get(settings.timeframe, 900000)
    last_open = kl[-1][0]
    close_time = last_open + interval
    now_ms = int(time.time() * 1000)
    if now_ms - close_time > interval * 2:
        return False, "stale candles"
    for k in kl:
        try:
            o, h, l, c = Decimal(str(k[1])), Decimal(str(k[2])), Decimal(str(k[3])), Decimal(str(k[4]))
            if h < l or c <= 0:
                return False, "invalid candle values"
        except Exception:
            return False, "malformed candle"
    return True, "ok"


def main():
    settings.fail_closed_if_inconsistent()
    lock = WorkerLock()
    if not lock.acquire():
        log.error("Another worker is running; exiting.")
        return

    storage = Storage()
    client = build_client()
    try:
        info = client.exchange_info()
    except Exception as e:
        log.error("exchange info failed: %s", e)
        info = {"symbols": []}
    engine = ExecutionEngine(client, storage, info)

    market_data = None
    if getattr(settings, "scan_all_usdt_perpetuals", True):
        market_data = MarketDataService(client)
        try:
            universe = market_data.refresh_universe()
            log.info("Market data universe: %s USDT perpetual symbols", len(universe))
        except Exception as e:
            log.warning("initial universe refresh failed: %s", e)
        market_data.start()

    orch = Orchestrator(client, storage, market_data=market_data)

    symbols_desc = f"{len(market_data.get_universe())} USDT perpetuals" if market_data else settings.symbol_list
    log.info("Starting bot in mode=%s live_authorized=%s symbols=%s", settings.trading_mode, settings.live_authorized, symbols_desc)
    storage.update_heartbeat("started")
    storage.log_event("SYSTEM", "", "worker", "started",
                      f"worker started; universe={symbols_desc}")
    storage.upsert_agent_status("SCANNER", "RUNNING", current_activity="started")
    storage.upsert_agent_status("EXECUTER", "IDLE", current_activity="ready")

    while True:
        try:
            storage.update_heartbeat("running")
            if orch.kill.is_halted()[0]:
                log.warning("Halted: %s", orch.kill.is_halted()[1])
                time.sleep(30)
                continue
            try:
                orch.run_cycle()
            except Exception as e:
                log.error("cycle failed: %s", e)
                storage.update_heartbeat("cycle_failed")
                time.sleep(10)
                continue
            time.sleep(settings.scan_interval_seconds)
        except KeyboardInterrupt:
            log.info("Shutting down")
            break
        except Exception as e:
            log.error("loop error: %s", e)
            storage.update_heartbeat("error")
            time.sleep(10)

    storage.update_heartbeat("stopped")
    if market_data is not None:
        market_data.close()
    lock.release()
    client.close()
    storage.close()


if __name__ == "__main__":
    main()