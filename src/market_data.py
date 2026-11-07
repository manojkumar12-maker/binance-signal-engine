"""Market data ingestion for every USDT-M perpetual contract.

A single background refresher downloads closed-candle history for the full
symbol universe on a pace that stays well inside Binance's request-weight
budget, persists it in SQLite, and lets the scanner evaluate every symbol
without touching the network on each cycle.
"""
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from .config import settings
from .storage import Storage

log = logging.getLogger("market_data")


class WeightLimiter:
    """Paced request-weight limiter (weights per minute).

    Reserves a slot per request so the average rate never exceeds the budget,
    including when several worker threads call acquire() at once.
    """

    def __init__(self, budget_per_min: int, window_seconds: int = 60):
        self.budget = max(1, int(budget_per_min))
        self.window = window_seconds
        self._interval = self.window / self.budget
        self._next_at = 0.0
        self._lock = threading.Lock()

    def acquire(self, weight: int = 1) -> None:
        weight = max(1, int(weight))
        with self._lock:
            now = time.monotonic()
            slot = max(now, self._next_at)
            self._next_at = slot + weight * self._interval
            wait = slot - now
        if wait > 0:
            time.sleep(wait)


class MarketDataService:
    def __init__(self, client, storage: Storage | None = None, intervals: list[str] | None = None,
                 limit: int | None = None, workers: int | None = None,
                 weight_per_min: int | None = None, refresh_seconds: int | None = None):
        self.client = client
        self._owns_storage = storage is None
        self.storage = storage or Storage()
        self.limit = int(limit or getattr(settings, "market_data_limit", 100))
        self.workers = max(1, int(workers or getattr(settings, "market_data_workers", 8)))
        self.refresh_seconds = int(refresh_seconds or getattr(settings, "market_data_refresh_seconds", 300))
        self.universe_refresh_seconds = int(getattr(settings, "market_data_universe_refresh_seconds", 3600))
        htf = getattr(settings, "timeframe", "15m")
        ltf = getattr(settings, "entry_timeframe", "5m")
        self.intervals = intervals or list(dict.fromkeys([htf, ltf]))
        self.limiter = WeightLimiter(weight_per_min or getattr(settings, "market_data_weight_per_min", 1200))
        self._lock = threading.RLock()
        self._stop = threading.Event()

    # ---------------------------------------------------------------- universe
    def refresh_universe(self) -> list[str]:
        self.limiter.acquire(1)
        info = self.client.exchange_info()
        rows = []
        for s in info.get("symbols", []):
            if (s.get("quoteAsset") == "USDT"
                    and s.get("contractType") == "PERPETUAL"
                    and s.get("status") == "TRADING"):
                rows.append(s.get("symbol"))
        rows = sorted(set(r for r in rows if r))
        if not rows:
            raise RuntimeError("exchangeInfo returned no USDT perpetual symbols")

        volumes = {}
        try:
            self.limiter.acquire(40)
            for t in self.client._request("GET", "/fapi/v1/ticker/24hr"):
                volumes[t.get("symbol")] = t.get("quoteVolume", "0")
        except Exception as e:
            log.warning("24h ticker fetch failed: %s", e)

        with self._lock:
            self.storage.save_market_universe([(s, volumes.get(s, "")) for s in rows])
            self.storage.set_market_meta("universe_updated", time.time())
        log.info("market universe refreshed: %s USDT perpetuals", len(rows))
        self.storage.log_event("SCANNER", "", "universe", "refreshed", f"{len(rows)} USDT perpetual symbols")
        return rows

    def get_universe(self) -> list[str]:
        with self._lock:
            symbols = self.storage.get_market_universe()
        if not symbols:
            try:
                symbols = self.refresh_universe()
            except Exception as e:
                log.warning("universe refresh failed: %s", e)
        return symbols

    # ------------------------------------------------------------------ prices
    def _fetch_symbol(self, symbol: str) -> tuple[str, dict]:
        data = {}
        last_error = None
        for interval in self.intervals:
            for attempt in range(2):
                try:
                    self.limiter.acquire(1)
                    kl = self.client.klines(symbol, interval, limit=self.limit)
                    if kl:
                        data[interval] = kl
                    break
                except Exception as e:
                    last_error = e
                    time.sleep(0.2 * (attempt + 1))
        if not data and last_error is not None:
            raise last_error
        return symbol, data

    def refresh_all(self, symbols: list[str] | None = None) -> dict:
        started = time.time()
        if symbols is None:
            symbols = self.get_universe()
            updated = 0.0
            try:
                with self._lock:
                    updated = float(self.storage.get_market_meta("universe_updated", 0) or 0)
            except Exception:
                updated = 0.0
            if not symbols or (time.time() - updated) >= self.universe_refresh_seconds:
                try:
                    symbols = self.refresh_universe()
                except Exception as e:
                    log.warning("universe refresh failed, using cached list: %s", e)
                    symbols = symbols or self.get_universe()

        stats = {"symbols": 0, "series": 0, "errors": 0, "duration": 0.0}
        pending = []

        def flush():
            if pending:
                with self._lock:
                    self.storage.save_market_candles_bulk(list(pending))
                pending.clear()

        with ThreadPoolExecutor(max_workers=self.workers) as ex:
            futures = [ex.submit(self._fetch_symbol, sym) for sym in symbols]
            for fut in as_completed(futures):
                try:
                    sym, data = fut.result()
                    stats["symbols"] += 1
                    for interval, kl in data.items():
                        pending.append((sym, interval, kl))
                        stats["series"] += 1
                    if len(pending) >= 200:
                        flush()
                except Exception as e:
                    stats["errors"] += 1
                    log.debug("market data fetch failed: %s", e)
        flush()

        stats["duration"] = round(time.time() - started, 1)
        stats["total"] = len(symbols)
        with self._lock:
            self.storage.set_market_meta("last_refresh", time.time())
            self.storage.set_market_meta("last_refresh_status", "ok")
            self.storage.set_market_meta("last_refresh_count", stats["series"])
            self.storage.set_market_meta("last_refresh_errors", stats["errors"])
            self.storage.set_market_meta("last_refresh_duration", stats["duration"])
        self.storage.log_event("SCANNER", "", "market_data", "refreshed",
                               f"symbols={stats['symbols']}/{len(symbols)} series={stats['series']} errors={stats['errors']} in {stats['duration']}s")
        log.info("market data refresh complete: symbols=%s/%s series=%s errors=%s duration=%ss",
                 stats["symbols"], len(symbols), stats["series"], stats["errors"], stats["duration"])
        return stats

    # ------------------------------------------------------------------- reads
    def get_klines(self, symbol: str, interval: str) -> list:
        with self._lock:
            candles, _ = self.storage.get_market_candles(symbol, interval)
        return candles

    def updated_at(self, symbol: str, interval: str) -> float:
        with self._lock:
            _, ts = self.storage.get_market_candles(symbol, interval)
        return ts

    def candles_count(self, symbol: str, interval: str) -> int:
        return len(self.get_klines(symbol, interval))

    def summary(self) -> dict:
        with self._lock:
            return self.storage.market_data_summary()

    # ------------------------------------------------------------------- loop
    def run_forever(self) -> None:
        log.info("market data refresher started (intervals=%s, workers=%s, budget=%s/min)",
                 self.intervals, self.workers, self.limiter.budget)
        while not self._stop.is_set():
            started = time.time()
            try:
                self.refresh_all()
            except Exception as e:
                log.error("market data refresh failed: %s", e)
                with self._lock:
                    self.storage.set_market_meta("last_refresh_status", f"error: {e}")
            elapsed = time.time() - started
            try:
                self._stop.wait(max(5, self.refresh_seconds - elapsed))
            except Exception:
                pass

    def start(self) -> threading.Thread:
        t = threading.Thread(target=self.run_forever, name="market-data", daemon=True)
        t.start()
        return t

    def stop(self) -> None:
        self._stop.set()

    def close(self) -> None:
        self.stop()
        if self._owns_storage:
            try:
                self.storage.close()
            except Exception:
                pass
