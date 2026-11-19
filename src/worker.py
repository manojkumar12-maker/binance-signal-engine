"""Main worker loop: monitor -> signal -> risk -> execute (demo by default)."""
import time
import logging
import threading
from .config import settings
from .binance_client import BinanceClient
from .orchestrator import Orchestrator
from .storage import Storage
from .settings_manager import SettingsManager
from .worker_lock import WorkerLock
from .market_data import MarketDataService

logging.basicConfig(level=getattr(logging, settings.log_level, logging.INFO))
log = logging.getLogger("worker")


def build_client() -> BinanceClient:
    key, secret = settings.credentials
    testnet = settings.use_testnet or settings.trading_mode != "live"
    c = BinanceClient(api_key=key, api_secret=secret, testnet=testnet)
    try:
        c.sync_time()
    except Exception as e:
        log.warning("time sync failed: %s", e)
    return c


def main():
    settings.fail_closed_if_inconsistent()
    lock = WorkerLock()
    if not lock.acquire():
        log.error("Another worker is running; exiting.")
        return

    storage = Storage()
    # Beat immediately so /api/health reports ok during slow startup
    # (client setup + universe refresh can take minutes on small VMs).
    storage.update_heartbeat("started")
    # Load credentials saved via the Settings page before building the client.
    SettingsManager(storage).load_into_settings()
    client = build_client()
    try:
        info = client.exchange_info()
    except Exception as e:
        log.error("exchange info failed: %s", e)
        info = {"symbols": []}
    market_data = None
    if getattr(settings, "scan_all_usdt_perpetuals", True):
        market_data = MarketDataService(client)
        try:
            universe = market_data.refresh_universe()
            log.info("Market data universe: %s USDT perpetual symbols", len(universe))
        except Exception as e:
            log.warning("initial universe refresh failed: %s", e)
        market_data.start()

    orch = Orchestrator(client, storage, market_data=market_data, exchange_info=info)

    # Heartbeat thread: beats every 30s while the pipeline shows progress
    # (loop iteration or orchestrator stage change), so /api/health no longer
    # reports degraded during scan cycles that legitimately run past the
    # 300s freshness window on small VMs. If nothing progresses for 20
    # minutes, the beats stop and the dashboard shows degraded.
    stage_ts = {"t": time.time(), "status": "started"}

    def _beat():
        while True:
            time.sleep(30)
            try:
                if time.time() - stage_ts["t"] < 1200:
                    storage.update_heartbeat(stage_ts["status"])
            except Exception:
                log.exception("heartbeat thread error")

    threading.Thread(target=_beat, daemon=True).start()
    _orig_set_stage = orch.set_stage

    def _set_stage(stage):
        stage_ts["t"] = time.time()
        _orig_set_stage(stage)

    orch.set_stage = _set_stage

    symbols_desc = f"{len(market_data.get_universe())} USDT perpetuals" if market_data else settings.symbol_list
    log.info("Starting bot in mode=%s live_authorized=%s symbols=%s", settings.trading_mode, settings.live_authorized, symbols_desc)
    storage.update_heartbeat("started")
    storage.log_event("SYSTEM", "", "worker", "started",
                      f"worker started; universe={symbols_desc}")
    storage.upsert_agent_status("SCANNER", "RUNNING", current_activity="started")
    storage.upsert_agent_status("EXECUTER", "IDLE", current_activity="ready")

    last_prune = 0.0
    while True:
        try:
            if time.time() - last_prune > 86400:
                try:
                    storage.prune_sessions()
                    storage.prune_seen_signals()
                    storage.prune_diagnostics(keep=10000)
                    storage.prune_logs(retention_days=30)
                except Exception:
                    log.exception("retention prune failed")
                last_prune = time.time()
            stage_ts["t"] = time.time()
            stage_ts["status"] = "running"
            storage.update_heartbeat("running")
            if orch.kill.is_halted()[0]:
                log.warning("Halted: %s", orch.kill.is_halted()[1])
                time.sleep(30)
                continue
            try:
                orch.run_cycle()
            except Exception as e:
                log.error("cycle failed: %s", e)
                stage_ts["t"] = time.time()
                stage_ts["status"] = "cycle_failed"
                storage.update_heartbeat("cycle_failed")
                time.sleep(10)
                continue
            time.sleep(settings.scan_interval_seconds)
        except KeyboardInterrupt:
            log.info("Shutting down")
            break
        except Exception as e:
            log.error("loop error: %s", e)
            stage_ts["t"] = time.time()
            stage_ts["status"] = "error"
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