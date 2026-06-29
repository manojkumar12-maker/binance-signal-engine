"""
Loads cached parquet klines and serves them as the same dict-list shape
that app.services.market.get_klines() returns, sliced up to a given point
in time so the strategy never sees future candles.
"""
import os
from typing import Dict, List, Optional

import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


def _df_to_candles(df: pd.DataFrame) -> List[Dict]:
    return [
        {
            "open_time": int(r.open_time),
            "open": float(r.open),
            "high": float(r.high),
            "low": float(r.low),
            "close": float(r.close),
            "volume": float(r.volume),
            "close_time": int(r.close_time),
        }
        for r in df.itertuples(index=False)
    ]


class HistoricalFeed:
    """
    Holds all cached candle data in memory for the pairs/intervals being
    backtested, and exposes get_klines(pair, interval, limit, as_of_ms) that
    mirrors market.get_klines(pair, interval, limit) but is time-bounded.
    """

    def __init__(self, market: str = "futures"):
        self.market = market
        self._cache: Dict[str, Dict[str, pd.DataFrame]] = {}

    def load(self, pair: str, intervals: List[str]):
        self._cache.setdefault(pair, {})
        for interval in intervals:
            path = os.path.join(DATA_DIR, self.market, pair, f"{interval}.parquet")
            if not os.path.exists(path):
                raise FileNotFoundError(
                    f"No cached data for {pair} {interval} at {path}. "
                    f"Run: python -m backtest.download_data --pairs {pair}"
                )
            df = pd.read_parquet(path)
            df = df.sort_values("open_time").reset_index(drop=True)
            self._cache[pair][interval] = df

    def get_klines(self, pair: str, interval: str, limit: int, as_of_ms: int) -> List[Dict]:
        """
        Returns up to `limit` candles whose open_time <= as_of_ms, i.e. the
        most recent `limit` candles available as of that point in simulated
        time. This is the no-lookahead guarantee: the strategy under test
        only ever sees this slice.
        """
        df = self._cache.get(pair, {}).get(interval)
        if df is None:
            return []

        visible = df[df["open_time"] <= as_of_ms]
        if visible.empty:
            return []

        window = visible.tail(limit)
        return _df_to_candles(window)

    def primary_timeline(self, pair: str, interval: str = "1h") -> List[int]:
        """All open_times for the primary backtest loop to step through."""
        df = self._cache.get(pair, {}).get(interval)
        if df is None:
            return []
        return df["open_time"].astype(int).tolist()

    def candle_at_or_after(self, pair: str, interval: str, ts_ms: int) -> Optional[Dict]:
        df = self._cache.get(pair, {}).get(interval)
        if df is None:
            return None
        row = df[df["open_time"] >= ts_ms].head(1)
        if row.empty:
            return None
        return _df_to_candles(row)[0]

    def candles_between(self, pair: str, interval: str, start_ms: int, end_ms: int) -> List[Dict]:
        df = self._cache.get(pair, {}).get(interval)
        if df is None:
            return []
        window = df[(df["open_time"] >= start_ms) & (df["open_time"] <= end_ms)]
        return _df_to_candles(window)
