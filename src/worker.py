"""Main worker loop: monitor -> signal -> risk -> execute (demo by default)."""
import time
import logging
from decimal import Decimal
from .config import settings, reload_settings
from .binance_client import BinanceClient
from .exchange_filters import get_symbol_info
from .signal_engine import SignalEngine
from .execution import ExecutionEngine
from .storage import Storage
from .kill_switch import KillSwitch
from .account import get_available_equity

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
    symbol = settings.symbol

    log.info("Starting bot in mode=%s live_authorized=%s", settings.trading_mode, settings.live_authorized)

    while True:
        try:
            if kill.is_halted()[0]:
                log.warning("Halted: %s", kill.is_halted()[1])
                time.sleep(30)
                continue
            # fetch klines
            try:
                kl = client.klines(symbol, settings.timeframe, 200)
                closes = [Decimal(str(k[4])) for k in kl]
            except Exception as e:
                log.error("klines failed: %s", e)
                time.sleep(10)
                continue

            signal = sig_engine.evaluate(symbol, settings.timeframe, closes)
            if signal is not None:
                log.info("Signal generated: %s %s @ %s", signal.direction, symbol, signal.entry_price)
                ok, reason = engine.execute_signal(signal, symbol)
                log.info("Execution result: %s %s", ok, reason)
                if not ok and "risk" in reason:
                    pass
            time.sleep(60)
        except KeyboardInterrupt:
            log.info("Shutting down")
            break
        except Exception as e:
            log.error("loop error: %s", e)
            time.sleep(10)

    client.close()
    storage.close()


if __name__ == "__main__":
    main()