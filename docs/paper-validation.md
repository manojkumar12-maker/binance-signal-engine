# Paper Validation Guide

## Verification
- Confirm `TRADING_MODE=paper` in environment.
- `GET /api/status` shows trading_mode=paper and live_authorized=false.
- Run for 48-72 hours.
- Check scanner cycles in logs.
- Verify signals saved in `/api/scanner/results`.
- Verify Rug Check runs.
- Verify sizer approvals/rejections.
- Verify paper executions in `/api/paper/trades`.
- Verify equity snapshots in `/api/equity/history`.
- Restart app and confirm no duplicate trades and positions monitored.

## Empty States
- If no valid signals, dashboard shows empty states; do not fabricate activity.
## Early-pump strategy validation (2026-11-22)

Added `BacktestConfig.strategy="early_pump"` — a surge-onset detector (volume
>= 3x the 20-candle average, close breaking the 24-candle high/low, prior
6% compression range, 1xATR stop / 4xATR target, same 2.5 net R:R fee gate).

Walk-forward, 3 disjoint out-of-sample splits, 1h candles May-Oct 2026,
$30 balance, 1% risk (data: data.binance.vision):

| Symbol | trades | win rate | net P&L | verdict |
|---|---|---|---|---|
| BTCUSDT  | 66 | 16.7% | -5.81 | NEGATIVE |
| ETHUSDT  | 77 | 18.2% | -6.97 | NEGATIVE |
| SOLUSDT  | 67 | 22.4% | -1.89 | NEGATIVE |

Tighter variants (4-6x volume, 3-4% squeeze) are fully filtered out by the
2.5 net fee gate: 0-1 trades. Conclusion: chasing pump onsets at 1h after
fees loses money in every variant tested; the trend strategy on BTCUSDT
(+1.41 net over the same period) remains the only positive configuration.
Do not route live capital to the pump detector.
