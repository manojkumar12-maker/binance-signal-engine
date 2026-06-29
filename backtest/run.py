"""
Main backtest loop.

For each pair, steps through its 1h candle timeline one bar at a time
(skipping a warm-up window so indicators have enough history), calls the
REAL, unmodified app.services.strategy.generate_signal() with the clock
pinned to that bar, and — if a tradeable signal comes back — simulates the
trade forward using simulator.simulate_trade().

Usage:
    python -m backtest.run --pairs BTCUSDT,ETHUSDT --start 2025-06-01 --end 2026-06-01
    python -m backtest.run --pairs BTCUSDT --start 2025-06-01 --end 2026-06-01 --step-hours 4
"""
import argparse
import json
import os
import sys
import time
import traceback
from datetime import datetime, timezone

import pandas as pd

# allow running as `python -m backtest.run` from repo root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from app.services import strategy

from backtest.data_feed import HistoricalFeed
from backtest.patcher import BacktestContext
from backtest.simulator import simulate_trade

WARMUP_CANDLES = 120  # needs >= config.CANDLE_LIMIT (100) of 1h history before first signal attempt
SIGNAL_COOLDOWN_HOURS = 4  # avoid spamming near-duplicate signals on the same pair every single bar


def ms_to_iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def run_pair(pair: str, feed: HistoricalFeed, start_ms: int, end_ms: int, step_hours: int):
    timeline = feed.primary_timeline(pair, "1h")
    timeline = [t for t in timeline if start_ms <= t <= end_ms]

    if len(timeline) < WARMUP_CANDLES + 10:
        print(f"  [SKIP] {pair}: not enough 1h candles in range ({len(timeline)})")
        return []

    results = []
    last_signal_ms = None

    with BacktestContext(feed) as ctx:
        i = WARMUP_CANDLES
        while i < len(timeline) - 1:
            ts = timeline[i]
            ctx.set_clock(ts)

            if last_signal_ms is not None and (ts - last_signal_ms) < SIGNAL_COOLDOWN_HOURS * 3600 * 1000:
                i += step_hours
                continue

            try:
                signal = strategy.generate_signal(pair, timeframe="1h", fetch_oi=False, use_closed_candles=False)
            except Exception as e:
                print(f"  [ERROR] {pair} @ {ms_to_iso(ts)}: {e}")
                traceback.print_exc()
                i += step_hours
                continue

            if signal.get("signal") in (None, "NO TRADE"):
                i += step_hours
                continue

            signal["_entry_time_ms"] = ts
            entry_idx_in_full_df = timeline.index(ts)
            future_candles = feed.candles_between(
                pair, "1h", ts + 3600 * 1000, end_ms
            )

            if not future_candles:
                i += step_hours
                continue

            outcome = simulate_trade(
                signal,
                future_candles,
                session=signal.get("current_session", "OFF"),
                regime_name=signal.get("regime", "UNKNOWN"),
            )

            results.append({
                "pair": pair,
                "entry_time": ms_to_iso(ts),
                "entry_time_ms": ts,
                "signal_type": signal.get("signal"),
                "confidence": signal.get("confidence"),
                "tier": signal.get("tier"),
                "regime": signal.get("regime"),
                "session": signal.get("current_session"),
                "setup_type": signal.get("setup_type"),
                "entry": signal.get("entry_primary"),
                "sl": signal.get("sl"),
                "tp1": signal.get("tp1"),
                "tp2": signal.get("tp2"),
                "tp3": signal.get("tp3"),
                "risk_pct": signal.get("risk_pct"),
                "outcome": outcome.outcome,
                "tp1_touch": outcome.tp1_touch,
                "tp2_touch": outcome.tp2_touch,
                "tp3_touch": outcome.tp3_touch,
                "realized_r": round(outcome.realized_r, 3),
                "raw_r_if_full_target": round(outcome.raw_r_if_full_target, 3),
                "bars_held": outcome.bars_held,
                "exit_time": ms_to_iso(outcome.exit_time_ms) if outcome.exit_time_ms else None,
            })

            last_signal_ms = ts
            i += step_hours

    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pairs", required=True, help="Comma-separated symbols, e.g. BTCUSDT,ETHUSDT")
    parser.add_argument("--start", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="YYYY-MM-DD")
    parser.add_argument("--market", choices=["spot", "futures"], default="futures")
    parser.add_argument("--step-hours", type=int, default=1,
                         help="Advance the clock by this many hours per loop iteration. "
                              "1 = check every candle (slow, thorough). Higher = faster, coarser.")
    args = parser.parse_args()

    pairs = [p.strip().upper() for p in args.pairs.split(",") if p.strip()]
    start_ms = int(datetime.strptime(args.start, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
    end_ms = int(datetime.strptime(args.end, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)

    feed = HistoricalFeed(market=args.market)
    all_results = []

    for pair in pairs:
        print(f"\n=== {pair} ===")
        feed.load(pair, ["1h", "4h", "15m", "5m"])
        t0 = time.time()
        pair_results = run_pair(pair, feed, start_ms, end_ms, args.step_hours)
        print(f"  {len(pair_results)} signals generated in {time.time() - t0:.1f}s")
        all_results.extend(pair_results)

    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(os.path.dirname(__file__), "results", f"run_{run_id}")
    os.makedirs(out_dir, exist_ok=True)

    df = pd.DataFrame(all_results)
    trades_path = os.path.join(out_dir, "trades.csv")
    df.to_csv(trades_path, index=False)

    meta = {
        "pairs": pairs,
        "start": args.start,
        "end": args.end,
        "market": args.market,
        "step_hours": args.step_hours,
        "total_signals": len(all_results),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "note": "OI data unavailable historically; fetch_oi forced False for all signals (see README).",
    }
    with open(os.path.join(out_dir, "meta.json"), "w") as f:
        json.dump(meta, f, indent=2)

    print(f"\nDone. {len(all_results)} total signals across {len(pairs)} pair(s).")
    print(f"Results: {trades_path}")
    print(f"Run: python -m backtest.report {out_dir}")


if __name__ == "__main__":
    main()
