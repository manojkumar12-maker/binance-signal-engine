"""
Monkey-patches the real app.services.market module (and the one real-clock
leak in structure.get_current_session) so that the UNMODIFIED
app.services.strategy.generate_signal() can be replayed against historical
data with zero lookahead.

This is intentionally invasive at the patch level so it can be completely
non-invasive at the source-code level: nothing in your actual app/ code
changes. The patch is active only for the lifetime of the `BacktestContext`
context manager.
"""
import contextlib
from datetime import datetime, timezone
from typing import Dict, List

from app.services import market as market_module
from app.services import structure as structure_module

from backtest.data_feed import HistoricalFeed

# Mirrors config.CANDLE_LIMIT default used throughout strategy.py
DEFAULT_LIMIT = 100

INTERVAL_TO_HOURS = {"5m": 5 / 60, "15m": 15 / 60, "1h": 1, "4h": 4}


def _session_for_hour(hour: int) -> str:
    # Mirrors app/services/structure.py:get_current_session exactly,
    # just driven by a supplied hour instead of datetime.utcnow().hour
    if 7 <= hour <= 12:
        return "LONDON"
    elif 13 <= hour <= 20:
        return "NY"
    elif 1 <= hour <= 6:
        return "ASIAN"
    else:
        return "OFF"


class BacktestContext:
    """
    Usage:
        feed = HistoricalFeed()
        feed.load("BTCUSDT", ["1h", "4h", "15m", "5m"])

        with BacktestContext(feed):
            # any call into app.services.strategy.generate_signal() during
            # this block will transparently use historical data as-of
            # whatever timestamp set_clock() was last called with.
            ctx.set_clock(some_timestamp_ms)
            signal = strategy.generate_signal(pair, timeframe="1h")
    """

    def __init__(self, feed: HistoricalFeed, oi_mode: str = "empty"):
        self.feed = feed
        self.oi_mode = oi_mode  # "empty" is the only supported mode in v1 - see README limitations
        self._clock_ms = None
        self._orig_get_klines = None
        self._orig_get_open_interest = None
        self._orig_get_current_session = None

    def set_clock(self, ts_ms: int):
        self._clock_ms = ts_ms

    def _patched_get_klines(self, symbol: str, interval: str = "1h", limit: int = DEFAULT_LIMIT) -> List[Dict]:
        if self._clock_ms is None:
            raise RuntimeError("BacktestContext clock not set - call set_clock() before generating a signal")
        return self.feed.get_klines(symbol, interval, limit, self._clock_ms)

    def _patched_get_open_interest(self, symbol: str) -> List[float]:
        # Binance's free OI endpoint has no historical lookup by past
        # timestamp, so OI is unavailable for backtesting. Returning []
        # mirrors what live get_open_interest() returns on any fetch
        # failure, which the existing volume.py / whale.py code already
        # handles gracefully. See README "Known limitations".
        return []

    def _patched_get_current_session(self) -> str:
        if self._clock_ms is None:
            return "OFF"
        hour = datetime.fromtimestamp(self._clock_ms / 1000, tz=timezone.utc).hour
        return _session_for_hour(hour)

    def __enter__(self):
        self._orig_get_klines = market_module.get_klines
        self._orig_get_open_interest = market_module.get_open_interest
        self._orig_get_current_session = structure_module.get_current_session

        market_module.get_klines = self._patched_get_klines
        market_module.get_open_interest = self._patched_get_open_interest
        structure_module.get_current_session = self._patched_get_current_session
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        market_module.get_klines = self._orig_get_klines
        market_module.get_open_interest = self._orig_get_open_interest
        structure_module.get_current_session = self._orig_get_current_session
        return False
