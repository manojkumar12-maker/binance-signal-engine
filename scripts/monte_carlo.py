"""Monte Carlo drawdown stress on a trade PnL series.

Usage:
  python -m scripts.monte_carlo --pnl 12,-8,5,... [--risk 0.01] [--equity 1000] [--runs 5000]
Or feed trades from the paper-trading DB:  --db data/bot.db
Shuffles trade order many times and reports the distribution of max drawdown
and risk-of-ruin style probabilities. Trade *sequence* risk only: it assumes
the trade set is representative and IID shuffling is a fair model.
"""
import argparse
import json
import os
import random
import sqlite3
import statistics
import sys


def load_trades_from_db(db_path):
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT pnl FROM trades WHERE pnl IS NOT NULL ORDER BY closed_at"
        ).fetchall()
    finally:
        conn.close()
    return [float(r[0]) for r in rows]


def parse_pnl(s):
    return [float(x) for x in s.split(",") if x.strip()]


def max_drawdown(equity):
    peak = equity[0]
    mdd = 0.0
    for e in equity:
        peak = max(peak, e)
        mdd = max(mdd, (peak - e) / peak)
    return mdd


def simulate(pnls, runs, equity0):
    mdds, finals, ruin = [], [], 0
    for _ in range(runs):
        random.shuffle(pnls)
        eq = [equity0]
        busted = False
        for p in pnls:
            nxt = eq[-1] + p
            if nxt <= 0:
                busted = True
                break
            eq.append(nxt)
        if busted:
            ruin += 1
            continue
        finals.append(eq[-1])
        mdds.append(max_drawdown(eq))
    return mdds, finals, ruin


def pct(sorted_vals, p):
    if not sorted_vals:
        return None
    i = min(len(sorted_vals) - 1, int(p / 100 * len(sorted_vals)))
    return sorted_vals[i]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pnl", help="comma-separated per-trade PnL in USDT")
    ap.add_argument("--db", help="path to bot.db (reads trades.pnl)")
    ap.add_argument("--equity", type=float, default=1000.0)
    ap.add_argument("--runs", type=int, default=5000)
    ap.add_argument("--ruin-level", type=float, default=0.2,
                    help="drawdown fraction considered 'ruin' (default 0.20)")
    args = ap.parse_args()

    if args.db:
        if not os.path.exists(args.db):
            sys.exit(f"no such db: {args.db}")
        pnls = load_trades_from_db(args.db)
    elif args.pnl:
        pnls = parse_pnl(args.pnl)
    else:
        sys.exit("provide --pnl or --db")

    if len(pnls) < 5:
        sys.exit(f"need >= 5 trades, got {len(pnls)}")

    mdds, finals, ruin = simulate(list(pnls), args.runs, args.equity)
    mdds.sort()
    finals.sort()
    ruin_level = args.ruin_level
    p_ruin_dd = sum(1 for m in mdds if m >= ruin_level) / max(len(mdds), 1)
    out = {
        "trades": len(pnls),
        "runs": args.runs,
        "net_pnl_usdt": round(sum(pnls), 4),
        "equity_start": args.equity,
        "max_drawdown": {
            "median_pct": round(statistics.median(mdds) * 100, 2) if mdds else None,
            "p95_pct": round(pct(mdds, 95) * 100, 2) if mdds else None,
            "worst_pct": round(mdds[-1] * 100, 2) if mdds else None,
        },
        f"p_drawdown_ge_{int(ruin_level*100)}_pct": round(p_ruin_dd, 4),
        "p_ruin_bankrupt": round(ruin / args.runs, 5),
        "final_equity": {
            "median": round(statistics.median(finals), 2) if finals else None,
            "p5": round(pct(finals, 5), 2) if finals else None,
        },
        "note": "Sequence risk only; assumes the trade sample is representative.",
    }
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
