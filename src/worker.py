"""Main worker loop: monitor -> signal -> risk -> execute (demo by default)."""
import time
import logging
import json
from decimal import Decimal
from .config import settings
from .binance_client import BinanceClient
from .signal_engine import SignalEngine
from .execution import ExecutionEngine
from .storage import Storage
from .kill_switch import KillSwitch
from .worker_lock import WorkerLock
from .reconciliation import ReconciliationService

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
    kill = KillSwitch(storage)
    sig_engine = SignalEngine(cooldown_seconds=settings.signal_cooldown_seconds)
    recon = ReconciliationService(client, storage)
    symbol = settings.symbol

    log.info("Starting bot in mode=%s live_authorized=%s", settings.trading_mode, settings.live_authorized)
    storage.update_heartbeat("started")

    while True:
        try:
            storage.update_heartbeat("running")
            if kill.is_halted()[0]:
                log.warning("Halted: %s", kill.is_halted()[1])
                time.sleep(30)
                continue

            try:
                r = recon.reconcile()
                storage.log_reconciliation(json.dumps(r))
                if r["discrepancies"]:
                    log.warning("Reconciliation discrepancies: %s", r["discrepancies"])
            except Exception as e:
                log.error("reconciliation failed: %s", e)
                storage.update_heartbeat("recon_failed")
                time.sleep(10)
                continue

            try:
                kl = client.klines(symbol, settings.timeframe, 200)
            except Exception as e:
                log.error("klines failed: %s", e)
                time.sleep(10)
                continue

            ok, reason = validate_candles(kl)
            if not ok:
                log.warning("Candle validation failed: %s", reason)
                time.sleep(10)
                continue

            closes = [Decimal(str(k[4])) for k in kl]
            interval = INTERVAL_MS.get(settings.timeframe, 900000)
            candle_close_time = kl[-1][0] + interval

            signal = sig_engine.evaluate(symbol, settings.timeframe, closes, candle_close_time=candle_close_time)
            if signal is not None:
                log.info("Signal generated: %s %s @ %s id=%s", signal.direction, symbol, signal.entry_price, signal.signal_id)
                if storage.is_signal_seen(signal.signal_id):
                    log.info("Duplicate signal skipped: %s", signal.signal_id)
                else:
                    storage.mark_signal_seen(signal.signal_id)
                    ok2, reason2 = engine.execute_signal(signal, symbol)
                    log.info("Execution result: %s %s", ok2, reason2)
                    if ok2 and not settings.live_authorized:
                        storage.save_signal(signal, accepted=False, reason="live not authorized; recorded only")
                    elif ok2:
                        storage.save_signal(signal, accepted=True)
                    else:
                        storage.save_signal(signal, accepted=False, reason=reason2)

            time.sleep(60)
        except KeyboardInterrupt:
            log.info("Shutting down")
            break
        except Exception as e:
            log.error("loop error: %s", e)
            storage.update_heartbeat("error")
            time.sleep(10)

    storage.update_heartbeat("stopped")
    lock.release()
    client.close()
    storage.close()


if __name__ == "__main__":
    main()