# Backtester for binance-signal-engine

Replays your existing `strategy.generate_signal()` logic against historical
candles — **unmodified** — and simulates each signal forward to see whether
SL, TP1, TP2, or TP3 was hit first. Produces a results CSV plus a summary
report sliced by tier, regime, session, and pair.

## Why monkey-patching, not refactoring

`generate_signal()` calls `market.get_klines()` (live HTTP) directly, four
times per call (1h/4h/15m/5m), plus `market.get_open_interest()`. Rather than
rewrite your strategy code to accept injected candles — which risks
introducing behavior differences between backtest and live — this harness
monkey-patches `app.services.market.get_klines` and `get_open_interest` for
the duration of the backtest run only. Your live code (`main.py`,
`execution_worker.py`, etc.) is completely untouched.

It also patches two real-clock dependencies that would otherwise leak
"today" into a historical replay:

- `structure.get_current_session()` — uses `datetime.utcnow()` internally.
  Patched to derive session from the candle's own `open_time` instead.
- `datetime.utcnow()` calls inside `strategy.py` for the `timestamp` field —
  cosmetic only (doesn't affect signal logic), left as-is, but the backtest
  report logs the *candle* timestamp separately so this doesn't matter.

## Install

```bash
cd binance-signal-engine
pip install -r requirements.txt
pip install -r backtest/requirements-backtest.txt
```

Add to your `.gitignore` so cached data and run outputs don't bloat the repo:
```
backtest/data/
backtest/results/
```


Copy this whole `backtest/` folder into your repo root (alongside `main.py`).

## 1. Download historical data

```bash
python -m backtest.download_data --pairs BTCUSDT,ETHUSDT,SOLUSDT --months 12
```

This pulls 1h, 4h, 15m, and 5m klines for each pair from Binance's public
klines REST endpoint (no API key needed — it's public market data) and
caches them as parquet files in `backtest/data/`. Re-running with the same
pairs/range will skip already-cached files unless you pass `--force`.

> Note: your `market.get_klines()` hits `BINANCE_API_URL` (spot), but you
> trade futures pairs via this engine. Spot and futures klines are usually
> near-identical but can diverge slightly (funding-driven basis, especially
> on alts during volatile periods). The downloader fetches **both** spot and
> futures klines and lets you pick which to backtest against with
> `--market spot|futures`. Default is `futures` since that's what you
> actually trade — this matters more than it sounds.

## 2. Run the backtest

```bash
python -m backtest.run --pairs BTCUSDT,ETHUSDT,SOLUSDT --start 2025-06-01 --end 2026-06-01
```

This steps through each pair's 1h candles one at a time, calling your real
`generate_signal()` at each step with only data available up to that candle
(no lookahead), and simulates the resulting trade forward bar-by-bar against
1h candles until SL/TP1/TP2/TP3 is hit or a max-hold timeout is reached.

Output: `backtest/results/run_<timestamp>/trades.csv` and `summary.json`.

## 3. View the report

```bash
python -m backtest.report backtest/results/run_<timestamp>/
```

Prints win rate, realized R:R, and trade count broken down by:
- confidence tier (SNIPER / A / B)
- detected regime (TRENDING / RANGE / TRANSITION / LOW_VOL)
- session (LONDON / NY / ASIAN / OFF)
- pair
- month (to catch regime drift over time)

It also reports two separate "win" definitions side by side, since your
80%-accuracy and 1:3 R:R goals are in tension:
- **TP1-touch rate**: did price reach TP1 before SL? (higher %, lower R:R)
- **Full-target rate**: did the trade run to TP3 (using your trailing-SL
  partial-exit logic from `trade_manager.py`) before being stopped out?

## Known limitations (read before trusting the numbers)

- **No slippage/fees modeled in v1.** Real fills will be worse. Treat backtest
  win rate as a ceiling, not a guarantee.
- **OI data**: `get_open_interest()` only returns *current* open interest, not
  historical OI — Binance's free OI endpoint doesn't serve historical OI at
  arbitrary past timestamps. The backtest serves OI as an empty list `[]` for
  every historical step, which slightly changes scoring vs. live (any
  OI-dependent score boosts/penalties in `scoring.py`/`whale.py` won't fire
  the same way). This is flagged explicitly in the summary report so it isn't
  silently ignored. If this matters a lot to your results, it's a sign your
  edge may be too OI-dependent to validate cheaply — worth knowing either way.
- **1h granularity for trade simulation.** SL/TP hit detection uses 1h
  high/low, so intra-candle order (did SL or TP hit first within the same
  candle?) is approximated conservatively (see `simulator.py` for the rule).
