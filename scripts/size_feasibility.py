#!/usr/bin/env python
"""Position-size feasibility for small accounts.

Answers the question: "at $X of capital, which Binance USDT-M perpetuals can I
actually open a correctly-sized trade on?" A signal is only tradable if the
risk-budgeted quantity clears the exchange LOT_SIZE / MIN_NOTIONAL filters and
the margin fits the account. This script fetches live public market data and
reports, per symbol, whether a trade is executable and why not.

Usage:
    python scripts/size_feasibility.py --balance 100 --leverage 1 --risk-pct 0.005
    python scripts/size_feasibility.py --balance 100 --timeframe 1h --json out.json

No API keys required (public market data only).
"""
import argparse
import json
import os
import sys
import time
from decimal import Decimal, ROUND_DOWN

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.indicators import atr
from src.exchange_filters import (
    get_lot_size_filter, get_min_notional_filter, round_quantity, validate_symbol_status,
)

BASE = "https://fapi.binance.com"
DEFAULT_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT",
]


def fetch_json(client, path, params=None):
    r = client.get(f"{BASE}{path}", params=params, timeout=20)
    r.raise_for_status()
    return r.json()


def get_klines(client, symbol, interval, limit=200):
    return fetch_json(client, "/fapi/v1/klines", {"symbol": symbol, "interval": interval, "limit": limit})


def atr_from_klines(klines, period=14):
    highs = [Decimal(str(k[2])) for k in klines]
    lows = [Decimal(str(k[3])) for k in klines]
    closes = [Decimal(str(k[4])) for k in klines]
    return atr(highs, lows, closes, period)


def analyze(symbol, info, price, klines, balance, leverage, risk_pct, atr_mult):
    row = {"symbol": symbol, "price": None, "atr": None, "stop_distance": None,
           "required_notional": None, "position_notional": None,
           "min_balance_needed": None, "feasible": False, "reason": ""}
    try:
        if not validate_symbol_status(info, symbol):
            row["reason"] = "not trading"
            return row
        price = Decimal(str(price))
        row["price"] = float(price)
        atr_val = atr_from_klines(klines)
        if atr_val is None or atr_val <= 0:
            row["reason"] = "insufficient kline history for ATR"
            return row
        stop_dist = atr_mult * atr_val
        row["atr"] = float(atr_val)
        row["stop_distance"] = float(stop_dist)

        lot = get_lot_size_filter(info, symbol)
        if lot is None:
            row["reason"] = "no LOT_SIZE filter"
            return row
        step = Decimal(str(lot["stepSize"]))
        min_qty = Decimal(str(lot["minQty"]))

        mn = get_min_notional_filter(info, symbol)
        min_notional = Decimal("0")
        if mn is not None:
            min_notional = Decimal(str(mn.get("notional", mn.get("minNotional", "0"))))

        # exchange minimum tradable quantity (qty AND notional floors)
        eff_min_qty = min_qty
        if min_notional > 0 and price > 0:
            eff_min_qty = max(min_qty, min_notional / price)
        required_notional = eff_min_qty * price
        row["required_notional"] = float(required_notional)

        # smallest balance that can place one valid trade at this risk %
        margin_need = required_notional / Decimal(leverage)
        risk_need = (eff_min_qty * stop_dist) / risk_pct
        min_balance = max(margin_need, risk_need)
        row["min_balance_needed"] = float(min_balance)

        risk_budget = balance * risk_pct
        if stop_dist <= 0:
            row["reason"] = "zero stop distance"
            return row
        qty_by_risk = risk_budget / stop_dist
        qty = round_quantity(qty_by_risk, step) if step > 0 else qty_by_risk
        notional = qty * price
        margin = notional / Decimal(leverage)
        row["position_notional"] = float(notional)

        if qty < min_qty:
            row["reason"] = f"risk budget too small (qty {qty} < minQty {min_qty})"
            return row
        if min_notional > 0 and notional < min_notional:
            row["reason"] = f"notional {notional:.2f} < minNotional {min_notional}"
            return row
        if margin > balance:
            row["reason"] = f"margin {margin:.2f} > balance {balance} at {leverage}x"
            return row
        row["feasible"] = True
        row["reason"] = "ok"
        return row
    except Exception as exc:  # noqa: BLE001 - report per-symbol failure, keep going
        row["reason"] = f"error: {type(exc).__name__}: {exc}"
        return row


def main():
    p = argparse.ArgumentParser(description="Binance position-size feasibility for a given capital.")
    p.add_argument("--balance", type=float, default=100.0, help="account equity in USDT")
    p.add_argument("--leverage", type=int, default=1, help="leverage to use")
    p.add_argument("--risk-pct", type=float, default=0.005, help="risk per trade as fraction of equity (0.005 = 0.5%%)")
    p.add_argument("--timeframe", default="1h", help="kline interval used for ATR (e.g. 1h, 4h)")
    p.add_argument("--atr-mult", type=float, default=1.5, help="stop distance in ATR multiples")
    p.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS), help="comma-separated symbols")
    p.add_argument("--json", dest="json_out", default="", help="write full results to this JSON file")
    args = p.parse_args()

    balance = Decimal(str(args.balance))
    leverage = max(1, args.leverage)
    risk_pct = Decimal(str(args.risk_pct))
    atr_mult = Decimal(str(args.atr_mult))
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]

    with httpx.Client() as client:
        info = fetch_json(client, "/fapi/v1/exchangeInfo")
        prices = {t["symbol"]: t["price"] for t in fetch_json(client, "/fapi/v1/ticker/price")}
        rows = []
        for i, sym in enumerate(symbols):
            try:
                kl = get_klines(client, sym, args.timeframe)
            except Exception as exc:  # noqa: BLE001
                rows.append({"symbol": sym, "feasible": False, "reason": f"kline error: {exc}"})
                continue
            rows.append(analyze(sym, info, prices.get(sym, "0"), kl, balance, leverage, risk_pct, atr_mult))
            if i < len(symbols) - 1:
                time.sleep(0.25)

    print(f"\nBalance ${args.balance:.2f} | leverage {leverage}x | risk {args.risk_pct*100:.2f}%/trade "
          f"| {args.atr_mult}x ATR stop on {args.timeframe}\n")
    header = f"{'SYMBOL':<10}{'PRICE':>12}{'STOP$':>10}{'NOTIONAL':>11}{'MIN BAL$':>11}  RESULT"
    print(header)
    print("-" * len(header))
    feasible = []
    for r in rows:
        if r.get("price") is None:
            print(f"{r['symbol']:<10}{'—':>12}{'—':>10}{'—':>11}{'—':>11}  NO  {r['reason']}")
            continue
        stop = r.get("stop_distance")
        notional = r.get("position_notional")
        minbal = r.get("min_balance_needed")
        stop_s = f"{stop:,.2f}" if stop is not None else "—"
        not_s = f"{notional:,.2f}" if notional is not None else "—"
        mb_s = f"{minbal:,.2f}" if minbal is not None else "—"
        verdict = "YES" if r["feasible"] else "NO "
        print(f"{r['symbol']:<10}{r['price']:>12,.4f}{stop_s:>10}{not_s:>11}{mb_s:>11}  {verdict} {r['reason']}")
        if r["feasible"]:
            feasible.append(r["symbol"])

    print(f"\nTradable at ${args.balance:.2f}: {len(feasible)}/{len(rows)} -> {', '.join(feasible) if feasible else 'NONE'}")
    if not feasible:
        cheapest = sorted(
            [r for r in rows if r.get("min_balance_needed") is not None],
            key=lambda r: r["min_balance_needed"],
        )
        if cheapest:
            c = cheapest[0]
            print(f"Smallest balance that can trade anything here: ~${c['min_balance_needed']:.2f} on {c['symbol']}")
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump({"params": vars(args), "rows": rows}, f, indent=2, default=str)
        print(f"Full results written to {args.json_out}")


if __name__ == "__main__":
    main()
