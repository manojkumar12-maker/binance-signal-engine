"""
Downloads historical klines for backtesting from Binance's PUBLIC market-data
endpoints (no API key required) and caches them as parquet.

Usage:
    python -m backtest.download_data --pairs BTCUSDT,ETHUSDT --months 12
    python -m backtest.download_data --pairs BTCUSDT --months 12 --market spot
    python -m backtest.download_data --pairs BTCUSDT --months 12 --force
"""
import argparse
import os
import time
from datetime import datetime, timedelta, timezone
from typing import List

import requests
import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

SPOT_BASE = "https://api.binance.com"
FUTURES_BASE = "https://fapi.binance.com"

INTERVALS = ["1h", "4h", "15m", "5m"]

# Binance caps klines at 1000 per request; we page backwards through time.
LIMIT = 1000

INTERVAL_MS = {
    "5m": 5 * 60 * 1000,
    "15m": 15 * 60 * 1000,
    "1h": 60 * 60 * 1000,
    "4h": 4 * 60 * 60 * 1000,
}


def _klines_url(market: str) -> str:
    if market == "futures":
        return f"{FUTURES_BASE}/fapi/v1/klines"
    return f"{SPOT_BASE}/api/v3/klines"


def fetch_klines_range(symbol: str, interval: str, start_ms: int, end_ms: int, market: str) -> List[list]:
    """Page through Binance klines from start_ms to end_ms (inclusive-ish)."""
    url = _klines_url(market)
    out = []
    cursor = start_ms
    step = INTERVAL_MS[interval] * LIMIT
    consecutive_failures = 0
    MAX_CONSECUTIVE_FAILURES = 5

    while cursor < end_ms:
        params = {
            "symbol": symbol,
            "interval": interval,
            "startTime": cursor,
            "limit": LIMIT,
        }
        try:
            resp = requests.get(url, params=params, timeout=15)
            resp.raise_for_status()
            batch = resp.json()
            consecutive_failures = 0
        except Exception as e:
            consecutive_failures += 1
            print(f"  [WARN] {symbol} {interval} fetch failed at {cursor} "
                  f"(attempt {consecutive_failures}/{MAX_CONSECUTIVE_FAILURES}): {e}")
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                print(f"  [FAIL] giving up on {symbol} {interval} after repeated failures. "
                      f"Check network/firewall access to {url}.")
                break
            time.sleep(2)
            continue

        if not batch:
            break

        out.extend(batch)
        last_open_time = batch[-1][0]

        if last_open_time <= cursor:
            # safety: avoid infinite loop if API returns no progress
            break

        cursor = last_open_time + INTERVAL_MS[interval]

        # be polite to the public endpoint
        time.sleep(0.25)

        if len(batch) < LIMIT:
            # reached the end of available data before end_ms
            break

    return [k for k in out if k[0] <= end_ms]


def klines_to_df(raw: List[list]) -> pd.DataFrame:
    cols = ["open_time", "open", "high", "low", "close", "volume", "close_time",
            "quote_volume", "trades", "taker_buy_base", "taker_buy_quote", "ignore"]
    df = pd.DataFrame(raw, columns=cols)
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = df[c].astype(float)
    df["open_time"] = df["open_time"].astype("int64")
    df["close_time"] = df["close_time"].astype("int64")
    return df[["open_time", "open", "high", "low", "close", "volume", "close_time"]]


def download_pair(symbol: str, months: int, market: str, force: bool = False):
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=months * 30)
    start_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)

    pair_dir = os.path.join(DATA_DIR, market, symbol)
    os.makedirs(pair_dir, exist_ok=True)

    for interval in INTERVALS:
        out_path = os.path.join(pair_dir, f"{interval}.parquet")
        if os.path.exists(out_path) and not force:
            print(f"  [SKIP] {symbol} {interval} (cached) -> {out_path}")
            continue

        print(f"  [FETCH] {symbol} {interval} {market} from {start.date()} to {end.date()}...")
        raw = fetch_klines_range(symbol, interval, start_ms, end_ms, market)
        if not raw:
            print(f"  [WARN] no data returned for {symbol} {interval}")
            continue

        df = klines_to_df(raw)
        df.to_parquet(out_path, index=False)
        print(f"  [OK] {symbol} {interval}: {len(df)} candles -> {out_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pairs", required=True, help="Comma-separated symbols, e.g. BTCUSDT,ETHUSDT")
    parser.add_argument("--months", type=int, default=12)
    parser.add_argument("--market", choices=["spot", "futures"], default="futures")
    parser.add_argument("--force", action="store_true", help="Re-download even if cached")
    args = parser.parse_args()

    pairs = [p.strip().upper() for p in args.pairs.split(",") if p.strip()]
    os.makedirs(DATA_DIR, exist_ok=True)

    print(f"Downloading {len(pairs)} pair(s), {args.months} months, market={args.market}")
    for pair in pairs:
        print(f"\n=== {pair} ===")
        download_pair(pair, args.months, args.market, force=args.force)

    print("\nDone. Data cached under backtest/data/")


if __name__ == "__main__":
    main()
