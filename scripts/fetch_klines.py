#!/usr/bin/env python
"""Fetch historical USDT-M futures klines from the public data.binance.vision mirror.

fapi.binance.com is geo-blocked from some machines (HTTP 451); the monthly
kline zips on data.binance.vision are the same data without API-key or weight
limits. Output is a JSON file of REST-shaped kline arrays (open_time, open,
high, low, close, volume, close_time, ...) that scripts/backtest_report.py
consumes via --data-file.

Usage:
    python scripts/fetch_klines.py --symbol BTCUSDT --interval 1h \
        --start 2026-01 --end 2026-11 --out data/BTCUSDT-1h.json
"""
import argparse
import io
import json
import os
import sys
import zipfile
from datetime import datetime, timezone

import httpx

BASE = "https://data.binance.vision/data/futures/um/monthly/klines"


def month_range(start: str, end: str):
    y, m = map(int, start.split("-"))
    ey, em = map(int, end.split("-"))
    while (y, m) <= (ey, em):
        yield f"{y:04d}-{m:02d}"
        m += 1
        if m > 12:
            y, m = y + 1, 1


def fetch_month(client: httpx.Client, symbol: str, interval: str, month: str) -> list:
    url = f"{BASE}/{symbol}/{interval}/{symbol}-{interval}-{month}.zip"
    r = client.get(url, timeout=60)
    if r.status_code == 404:
        return []
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        name = z.namelist()[0]
        text = z.read(name).decode("utf-8")
    out = []
    for line in text.splitlines():
        parts = line.split(",")
        if parts[0] == "open_time":
            continue
        out.append([int(parts[0]), parts[1], parts[2], parts[3], parts[4],
                    parts[5], int(parts[6]), *parts[7:]])
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--symbol", required=True)
    p.add_argument("--interval", default="1h")
    p.add_argument("--start", required=True, help="first month, YYYY-MM")
    p.add_argument("--end", required=True, help="last month, YYYY-MM")
    p.add_argument("--out", required=True, help="output JSON path")
    args = p.parse_args()

    klines = []
    with httpx.Client() as client:
        for month in month_range(args.start, args.end):
            batch = fetch_month(client, args.symbol, args.interval, month)
            print(f"{args.symbol} {args.interval} {month}: {len(batch)} candles")
            klines.extend(batch)

    # dedupe by open time, keep order
    seen, clean = set(), []
    for k in klines:
        if k[0] in seen:
            continue
        seen.add(k[0])
        clean.append(k)
    klines = clean

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(klines, f)
    if klines:
        first = datetime.fromtimestamp(klines[0][0] / 1000, tz=timezone.utc)
        last = datetime.fromtimestamp(klines[-1][0] / 1000, tz=timezone.utc)
        print(f"wrote {len(klines)} candles ({first:%Y-%m-%d} -> {last:%Y-%m-%d}) to {args.out}")


if __name__ == "__main__":
    main()
