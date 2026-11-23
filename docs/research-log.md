# Research Log — binance-signal-engine

Persistent record per the research standard. Failed experiments are kept, never erased.

## S-001: Trend strategy (evaluate_v2), BTCUSDT 1h

- **Discovered:** pre-2026-11 (inherited engine default)
- **Hypothesis:** regime-filtered trend continuation with ATR stops captures directional drift net of fees
- **Rules (reproducible):** `SignalEngine.evaluate_v2` — HTF (1h) trend regime gate; SL = 1.5×ATR, TP = 4.5×ATR (gross R:R 3.0); entry only if net reward/total loss ≥ 2.5 after taker fees (0.05%) + slippage (0.05%); risk 1% equity/trade; daily stop 3%; kill switch at daily budget; max 1 new entry/day, 3 concurrent positions
- **Data:** data.binance.vision futures UM 1h klines, 2026-05-01 → 2026-10-31 (4,416 candles BTC), daily files to 2026-11-21
- **Code version:** master `2717800`
- **Walk-forward OOS (3 disjoint splits, $30, 1% risk):**
  - BTCUSDT: 21 trades, 47.6% WR, net +1.41 USDT, PF 1.37, max DD 8.4%
  - ETHUSDT: 58 trades, 31.0% WR, net −3.29 — **REJECTED for ETH**
  - SOLUSDT: 67 trades, 22.4% WR, net −0.05 — flat, rejected
- **Metrics (BTC OOS trades):** avg win 0.52 / avg loss 0.34 (1.51:1 realized), expectancy 0.067 USDT/trade, PF 1.37
- **Monte Carlo (2,000 shuffles of 21 OOS trades):** median max DD 1.64, 95th pct 2.60, worst 3.73 USDT; P(DD > 20% of $30) = 0.0% at 1% risk
- **Paper replay (production PaperTrader, 30 days Nov, 4 symbols):** 14 trades, 7W/7L, net +3.42 USDT (+11.4%), fees 0.22 — flattered by a one-way downtrend; treated as pipeline validation, not edge evidence
- **Weaknesses:** only 21 OOS trades (far below the 50-trade minimum); one split (PF 9.59) carries the result — single-period dependence not excluded; regime coverage thin (May–Oct 2026 only); no benchmark comparison yet; short-bias benefited from a falling market
- **Status:** CONTINUE PAPER TRADING (BTC only)
- **Next actions:** testnet live-paper ≥ 50 trades; benchmark vs buy-and-hold BTC; add 2026 bull/chop regimes to the test set

### Cycle 2 (2026-11-22): extended OOS + benchmark — edge thinner than Cycle 1 suggested

- **Tooling:** added `scripts/fetch_klines.py` (data.binance.vision monthly zips → JSON) and `--data-file` offline mode for `scripts/backtest_report.py`; data dir `data/*.json` holds Jan–Oct 2026 1h klines (7,296 candles/symbol, 13 symbols). Commit `03cab45`.
- **Extended walk-forward (BTC, 6 disjoint OOS splits, 10 months Jan–Oct 2026, $30, 1% risk):** 65 trades, 36.9% WR, net **+0.22 USDT**, fees 1.96, PF 0.92–1.0 band across splits; split 1 (Jan–Feb) net +0.60 / DD 11.8%, weakest splits negative (one split −0.44, PF 0.92).
- **Verdict on sample size:** the 50-trade requirement is now met, and the measured edge is much smaller than Cycle 1's 3-split estimate (+1.41 on 21 trades). Cycle 1 result was single-period luck-weighted; full-year expectancy is ≈ +0.003 USDT/trade on $30 — essentially breakeven after fees.
- **Benchmark (buy-and-hold BTC, same windows, 1× notional):** −11.51% over 10 months (−3.45 USDT on $30); sum of split returns −7.36%. Strategy +0.22 vs benchmark −3.45 → the edge is **regime-defensive** (loses little in downtrends/chop, doesn't capture bull moves) rather than absolute alpha.
- **Monte Carlo (2,000 shuffles of the 71-trade OOS sample, seed 42):** median max DD 3.98, 95th pct 6.14, worst 8.09 USDT; **P(DD > 20% of $30) = 5.8%** — materially worse than the Cycle-1 21-trade estimate (0%), as expected with more data.
- **Decision impact:** S-001 remains paper-only. The optimistic growth path ($30→$450 in 12 months) requires expectancy ≥ 0.05 USDT/trade; the 65-trade OOS estimate is ~0.003. The path is NOT supported by current evidence; revisit after testnet paper trades accumulate and a chop-regime retest.

## S-002: Early-pump surge-onset detector — REJECTED

- **Hypothesis:** entering volume-surge breakouts from compression (3× volume, 24-candle breakout, ≤6% squeeze; 1×ATR SL / 4×ATR TP, 2.5 net gate) catches pumps early
- **Walk-forward OOS (same data/method):** BTC 66 trades 16.7% WR net −5.81; ETH 77 trades 18.2% WR net −6.97; SOL 67 trades 22.4% WR net −1.89
- **Stricter variants (4–6× volume, 3–4% squeeze):** filtered to ~0 trades by the fee gate
- **Reason for rejection:** negative expectancy net of fees in every variant; consistent with post-surge mean reversion and fee drag on wide ATR stops
- **Status:** REJECTED — do not route capital; kept as evidence

## S-003: 15-minute volume-change scanner filter

- **What:** ranks symbols by last-15-min volume vs baseline; scans only top N (default 10)
- **Status:** PARTIALLY VERIFIED as an execution filter (unit-tested; live ranking exercise done on real data). UNVERIFIED as an edge — no P&L attribution yet
- **Next action:** A/B paper comparison: top-N filtered vs full universe, 4 weeks

## Costs & small-account reality (verified)

- Assumptions used: taker 0.05%/side, slippage 0.05%, ~0.2% round-trip of notional
- At $30 with 1% risk ($0.30/trade), a 0.2% round-trip cost is ~10% of the risk budget on a 0.4%-stop trade — the 2.5:1 net gate exists because of this; maker entries (0.02% fee) are implemented as mitigation
- Binance futures min notional ~5 USDT and lot-size steps are enforced by `exchange_filters.py`
- Timeline math at measured edge (0.067 USDT/trade on $30, ~0.7 trades/day): if it held, ~100× takes years, not weeks. Not guaranteed; the edge itself is not yet proven to persist.
