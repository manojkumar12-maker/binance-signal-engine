#!/usr/bin/env python
"""Run the Signal Engine V2 backtester on real Binance history.

Fetches public USDT-M futures klines (no API key needed), runs the project's
own Backtester, and applies real exchange LOT_SIZE / MIN_NOTIONAL filters so the
report shows both performance and how many otherwise-valid signals a small
account cannot actually execute.

Usage:
    python scripts/backtest_report.py --balance 100 --symbols BTCUSDT,ETHUSDT
    python scripts/backtest_report.py --balance 100 --days 365 --interval 1h
    python scripts/backtest_report.py --json report.json
"""
import argparse
import json
import os
import sys
import time
from decimal import Decimal

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.backtest import Backtester, BacktestConfig, walk_forward

BASE = "https://fapi.binance.com"


def fetch_json(client, path, params=None):
    r = client.get(f"{BASE}{path}", params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def fetch_history(client, symbol, interval, start_ms, end_ms, page=1500):
    out = []
    cursor = start_ms
    while cursor < end_ms:
        batch = fetch_json(client, "/fapi/v1/klines", {
            "symbol": symbol, "interval": interval, "limit": page,
            "startTime": cursor, "endTime": end_ms,
        })
        if not batch:
            break
        out.extend(batch)
        if len(batch) < page:
            break
        cursor = int(batch[-1][0]) + 1
        time.sleep(0.25)
    # dedupe by open time, keep order
    seen = set()
    clean = []
    for k in out:
        if k[0] in seen:
            continue
        seen.add(k[0])
        clean.append(k)
    return clean


def print_report(rep, label):
    print(f"\n=== {label} ===")
    print(f"  trades            : {rep['total_trades']}")
    print(f"  win rate          : {rep['win_rate_pct']}%")
    print(f"  avg R / trade     : {rep['avg_r_multiple']}R")
    print(f"  profit factor     : {rep['profit_factor']}")
    print(f"  net P&L           : {rep['net_pnl']} USDT")
    print(f"  total fees        : {rep['total_fees']} USDT")
    print(f"  max drawdown      : {rep['max_drawdown']} USDT ({rep['max_drawdown_pct']}%)")
    print(f"  final equity      : {rep['final_equity']} USDT")
    print(f"  rejected signals  : {rep.get('rejected_signals', 0)}  {rep.get('rejections_by_reason', {})}")


def main():
    p = argparse.ArgumentParser(description="Backtest Signal Engine V2 on real Binance history.")
    p.add_argument("--symbols", default="BTCUSDT,ETHUSDT", help="comma-separated symbols")
    p.add_argument("--interval", default="1h", help="timeframe (1h, 4h, 15m ...)")
    p.add_argument("--days", type=int, default=180, help="lookback in days")
    p.add_argument("--balance", type=float, default=100.0, help="starting equity USDT")
    p.add_argument("--risk-pct", type=float, default=0.01, help="risk per trade fraction (0.01 = 1%%)")
    p.add_argument("--min-score", type=float, default=75.0, help="minimum signal score")
    p.add_argument("--lookback", type=int, default=400, help="rolling candles passed to engine (0 = full; 400 = fast)")
    p.add_argument("--walk-forward", type=int, default=0, metavar="N",
                   help="run N disjoint out-of-sample splits instead of a single full-window backtest")
    p.add_argument("--taker-fee", type=float, default=0.0005)
    p.add_argument("--maker-fee", type=float, default=0.0002)
    p.add_argument("--slippage", type=float, default=0.0005)
    p.add_argument("--data-file", default="",
                   help="JSON file of klines (from scripts/fetch_klines.py) instead of live fetching; "
                        "single symbol only")
    p.add_argument("--json", dest="json_out", default="", help="write full results to JSON")
    args = p.parse_args()

    now_ms = int(time.time() * 1000)
    start_ms = now_ms - args.days * 86_400_000
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]

    results = {}
    with httpx.Client() as client:
        info = None
        if not args.data_file:
            try:
                info = fetch_json(client, "/fapi/v1/exchangeInfo")
            except Exception as exc:  # noqa: BLE001
                print(f"Failed to fetch exchangeInfo: {exc}")
                sys.exit(1)

        cfg = BacktestConfig(
            starting_balance=Decimal(str(args.balance)),
            risk_per_trade_pct=Decimal(str(args.risk_pct)),
            min_score=args.min_score,
            taker_fee=Decimal(str(args.taker_fee)),
            maker_fee=Decimal(str(args.maker_fee)),
            slippage=Decimal(str(args.slippage)),
            htf=args.interval,
            ltf=args.interval,
            max_lookback=args.lookback,
            exchange_info=info,
        )

        if args.data_file:
            with open(args.data_file, encoding="utf-8") as f:
                cached = json.load(f)
            if len(symbols) != 1:
                print("--data-file takes exactly one --symbols entry")
                sys.exit(1)
            sym = symbols[0]
            print(f"{sym}: loaded {len(cached)} {args.interval} candles from {args.data_file}")
            klines_by_symbol = {sym: cached}
        else:
            klines_by_symbol = {}
            for sym in symbols:
                try:
                    klines_by_symbol[sym] = fetch_history(client, sym, args.interval, start_ms, now_ms)
                except Exception as exc:  # noqa: BLE001
                    print(f"\n{sym}: kline fetch failed: {exc}")
        for sym, kl in klines_by_symbol.items():
            if not args.data_file:
                print(f"\n{sym}: fetched {len(kl)} {args.interval} candles over ~{args.days} days")
            if len(kl) < 200:
                print(f"  not enough history ({len(kl)}), skipping")
                continue
            if args.walk_forward > 0:
                wf = walk_forward(sym, kl, None, n_splits=args.walk_forward, cfg=cfg)
                oos = wf["splits"]
                tot = sum(r["total_trades"] for r in oos)
                wins = sum(r["wins"] for r in oos)
                net = sum(Decimal(str(r["net_pnl"])) for r in oos)
                fees = sum(Decimal(str(r["total_fees"])) for r in oos)
                wr = round(wins / tot * 100, 2) if tot else 0.0
                for n, rep in enumerate(oos, 1):
                    print_report(rep, f"{sym} OOS split {n}/{len(oos)} ({rep.get('split', '')})")
                print(f"\n=== {sym} WALK-FORWARD (out-of-sample, all {len(oos)} splits) ===")
                print(f"  trades            : {tot}")
                print(f"  win rate          : {wr}%")
                print(f"  net P&L           : {net} USDT")
                print(f"  total fees        : {fees} USDT")
                print(f"  EXPECTANCY        : {'POSITIVE' if net > 0 else 'NEGATIVE/FLAT'}")
                results[sym] = oos[-1]
                results[sym + "_wf"] = {"total_trades": tot, "wins": wins, "win_rate_pct": wr,
                                        "net_pnl": str(net), "total_fees": str(fees)}
                continue
            bt = Backtester(cfg)
            rep = bt.run(sym, kl, None)
            results[sym] = rep
            print_report(rep, f"{sym} @ {args.interval}")

    if len(results) > 1:
        print("\n=== AGGREGATE ===")
        tot = sum(r["total_trades"] for r in results.values())
        wins = sum(r["wins"] for r in results.values())
        wr = round(wins / tot * 100, 2) if tot else 0.0
        net = sum(Decimal(r["net_pnl"]) for r in results.values())
        print(f"  symbols={len(results)} trades={tot} win_rate={wr}% net_pnl={net} USDT")
        print(f"  rejected_signals={sum(r.get('rejected_signals', 0) for r in results.values())}")

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\nFull results written to {args.json_out}")


if __name__ == "__main__":
    main()
