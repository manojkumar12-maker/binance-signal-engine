"""
Summarizes a backtest run's trades.csv into win-rate / R:R breakdowns.

Usage:
    python -m backtest.report backtest/results/run_20260628_143000/
"""
import argparse
import json
import os

import pandas as pd


def _slice_stats(df: pd.DataFrame, group_col: str) -> pd.DataFrame:
    resolved = df[df["outcome"] != "TIMEOUT"]
    grouped = resolved.groupby(group_col).agg(
        trades=("outcome", "count"),
        tp1_touch_rate=("tp1_touch", "mean"),
        full_target_rate=("tp3_touch", "mean"),
        avg_realized_r=("realized_r", "mean"),
        win_rate_realized_positive=("realized_r", lambda s: (s > 0).mean()),
    ).round(3)
    grouped = grouped.sort_values("trades", ascending=False)
    return grouped


def print_section(title: str, table: pd.DataFrame):
    print(f"\n--- {title} ---")
    if table.empty:
        print("  (no resolved trades)")
        return
    print(table.to_string())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", help="Path to backtest/results/run_<id>/")
    args = parser.parse_args()

    trades_path = os.path.join(args.run_dir, "trades.csv")
    meta_path = os.path.join(args.run_dir, "meta.json")

    df = pd.read_csv(trades_path)
    with open(meta_path) as f:
        meta = json.load(f)

    print(f"Run: {args.run_dir}")
    print(f"Pairs: {meta['pairs']}")
    print(f"Range: {meta['start']} to {meta['end']} ({meta['market']})")
    print(f"Total signals: {meta['total_signals']}")
    if meta.get("note"):
        print(f"NOTE: {meta['note']}")

    if df.empty:
        print("\nNo signals were generated in this range. Either the strategy is very")
        print("selective, or something upstream is filtering everything out — check")
        print("MIN_CONFIDENCE / MIN_SNIPER_CONFIDENCE in config.py against what's")
        print("actually being scored before concluding the strategy has no edge here.")
        return

    timeout_n = (df["outcome"] == "TIMEOUT").sum()
    resolved_n = len(df) - timeout_n
    print(f"\nResolved trades: {resolved_n}  |  Timed out (no SL/TP hit in window): {timeout_n}")

    resolved = df[df["outcome"] != "TIMEOUT"]
    if resolved.empty:
        print("All trades timed out - widen the date range or check MAX_HOLD_CANDLES.")
        return

    overall_tp1 = resolved["tp1_touch"].mean()
    overall_full = resolved["tp3_touch"].mean()
    overall_r = resolved["realized_r"].mean()
    overall_winrate = (resolved["realized_r"] > 0).mean()

    print("\n=== OVERALL ===")
    print(f"TP1-touch rate (reached TP1 before SL):      {overall_tp1:.1%}")
    print(f"Full-target rate (reached TP3 before SL):    {overall_full:.1%}")
    print(f"Win rate (realized R > 0, partials+trail):   {overall_winrate:.1%}")
    print(f"Average realized R per trade:                {overall_r:+.2f}R")
    print()
    print("Reminder: your 80% accuracy goal and 1:3 R:R goal pull in opposite")
    print("directions. TP1-touch rate is the closest analogue to a traditional")
    print('"accuracy" number but its R:R is much lower than 1:3. Full-target rate')
    print("is closer to a true 1:3 trade but will be a much lower hit rate.")
    print("Decide which one 'accuracy' means for you before judging these numbers.")

    print_section("By confidence tier", _slice_stats(df, "tier"))
    print_section("By regime", _slice_stats(df, "regime"))
    print_section("By session", _slice_stats(df, "session"))
    print_section("By pair", _slice_stats(df, "pair"))

    df["entry_month"] = pd.to_datetime(df["entry_time"]).dt.strftime("%Y-%m")
    print_section("By month (watch for regime drift / overfitting to one period)",
                   _slice_stats(df, "entry_month"))


if __name__ == "__main__":
    main()
