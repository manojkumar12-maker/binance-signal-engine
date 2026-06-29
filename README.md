# Binance Signal Engine

A professional-grade algorithmic trading system for Binance USDT futures that combines Smart Money Concepts (SMC) with quantitative risk management.

---

## Features

### Signal Generation
- **Multi-timeframe alignment** (4H → 1H → 15M → 5M)
- **Structure detection** (trend, liquidity sweeps, BOS, CHoCH)
- **Order Block detection** (single TF and multi-TF stacked)
- **FVG (Fair Value Gap) detection**
- **VWAP bias filtering**

### Scoring & Classification
- **Split scoring system** (structure 65% + execution 35%)
- **Tier classification** (SNIPER → A → B → REJECT)
- **RR-based confidence boost** and position sizing
- **Session filtering** (soft penalty system)
- **Volatility mode adaptation**
- **Location filter** (price in range)

### Risk Management
- **Partial TP** (50% at TP1, trailing SL)
- **Position limits** (max 3 trades, 1 per sector)
- **Kill switch** (drawdown protection)
- **Correlation-based selection**

### Broker & Real Trading
- **Dedicated broker layer** (`broker.py`) — single point of contact for Binance Futures
- **HMAC signing** via `python-binance` SDK (no hand-rolled crypto)
- **Kill-switch gate** checked before every order (drawdown + daily loss)
- **Idempotent order IDs** (`newClientOrderId`) to prevent double-fills
- **Reconciliation loop** — compares internal trades vs exchange positions every 30s
- **Testnet support** — point at `testnet.binancefuture.com` first
- **Sim mode** — `BROKER_ENABLED=false` returns simulated fills, no real API calls

### Backtesting
- **Historical replay** — monkey-patches `market.get_klines()` to serve parquet-backed data with no lookahead
- **Trade simulator** — partial-TP, trailing-stop, SL/TP hit detection
- **Report generator** — win rate, R:R breakdowns by tier, regime, session, pair

### Execution
- **Microstructure filtering** (delta, absorption)
- **Self-learning loop** (adaptive weights)
- **Telegram alerts**

---

## Architecture

```
Scanner (60s) → Signal Generation → Filters → Scoring → Tier Classification
                                                          ↓
                                                       Selection (correlation)
                                                          ↓
                                                Execution → Risk Engine → Broker
                                                                        (Binance Futures API)
                                                          ↓
                                                       Tracking → Self-Learning
                                                          ↓
                                                    Reconciliation (30s cycle)
```

---

## Broker Safety Features

| Feature | Description |
|---------|-------------|
| **Kill switch** | Checked before every order. Blocks trading if drawdown ≥ 7% or daily loss ≥ 3%. |
| **Idempotency** | `newClientOrderId = sig_{pair}_{side}_{ms}` prevents double-fills on retry. |
| **Reconciliation** | Every 30s, open internal trades are compared against Binance position risk. Mismatches are logged. |
| **Retry logic** | Rate-limited retries with exponential backoff (3 attempts max). |
| **Testnet first** | `USE_TESTNET=true` routes all orders to testnet.binancefuture.com. |
| **Sim mode** | `BROKER_ENABLED=false` (default) — no API keys needed, all orders simulated. |

---

## Go-Live Checklist

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set credentials
export BINANCE_API_KEY=your_key
export BINANCE_API_SECRET=your_secret
export USE_TESTNET=true    # start on testnet
export BROKER_ENABLED=true

# 3. Run on testnet and verify orders appear at:
#    https://testnet.binancefuture.com/

# 4. Switch to mainnet
export USE_TESTNET=false
```

---

## Configuration

| Parameter | Default | Description |
|-----------|--------|------------|
| `MIN_CONFIDENCE` | 70 | Minimum confidence to emit signal |
| `MIN_RR_RATIO` | 1.5 | Minimum risk:reward ratio |
| `MAX_OPEN_TRADES` | 3 | Maximum open positions |
| `MAX_PER_SECTOR` | 1 | Maximum per sector |
| `SNIPER_MODE_ONLY` | false | Only execute SNIPER tier |
| `BROKER_ENABLED` | false | Enable real Binance orders |
| `USE_TESTNET` | true | Route orders to testnet |
| `RECONCILE_INTERVAL_SECONDS` | 30 | Position reconciliation interval |

---

## API Endpoints

| Endpoint | Description |
|----------|------------|
| `/api/signal/<pair>` | Get signal for pair |
| `/api/signals` | Get cached signals |
| `/api/trades` | Get open/closed trades |
| `/api/config` | Get/set config |
| `/api/self-learning` | Performance analytics |
| `/api/system-status` | Pipeline status |

---

## Tier System

| Tier | Confidence | Entry Score | Action |
|------|-----------|------------|--------|
| SNIPER | ≥85 | ≥80 | Execute with higher size |
| A | ≥78 | ≥70 | Execute normal |
| B | ≥70 | - | Execute with reduced size |
| REJECT | <70 | - | Skip |

---

## Installation

```bash
pip install -r requirements.txt
pip install -r backtest/requirements-backtest.txt   # for backtesting
python main.py
```

---

## Backtesting

```bash
# 1. Download historical data
python -m backtest.download_data --pairs BTCUSDT,ETHUSDT,SOLUSDT --months 12

# 2. Run backtest
python -m backtest.run --pairs BTCUSDT,ETHUSDT,SOLUSDT --start 2025-06-01 --end 2026-06-01

# 3. Generate report
python -m backtest.report backtest/results/run_<timestamp>/
```

---

## Running

```bash
python main.py
# Server starts on port 8000
```

---

## Docker

```bash
docker build -t binance-signal-engine .
docker run -p 8000:8000 binance-signal-engine
```

---

## Environment Variables

| Variable | Description |
|----------|------------|
| `TELEGRAM_BOT_TOKEN` | Telegram bot token |
| `TELEGRAM_CHAT_ID` | Telegram chat ID |
| `PORT` | Server port (default 8000) |
| `BINANCE_API_KEY` | Binance API key |
| `BINANCE_API_SECRET` | Binance API secret |
| `BROKER_ENABLED` | Enable real trading (`true`/`false`) |
| `USE_TESTNET` | Route orders to testnet (`true`/`false`) |

---

## File Structure

```
binance-signal-engine/
├── main.py                 # Flask server + scanner
├── config.py               # Configuration
├── dashboard.html          # UI dashboard
├── backtest/               # Historical backtesting
│   ├── run.py              # Backtest loop
│   ├── download_data.py    # Historical data fetcher
│   ├── data_feed.py        # No-lookahead data server
│   ├── patcher.py          # Monkey-patch module
│   ├── simulator.py        # Trade simulation
│   ├── report.py           # Performance report generator
│   └── data/               # Cached parquet files
├── app/
│   └── services/
│       ├── strategy.py       # Signal generation
│       ├── scoring.py        # Confidence calculation
│       ├── structure.py      # Market structure
│       ├── liquidity.py      # Liquidity detection
│       ├── volume.py         # Volume analysis
│       ├── whale.py          # Whale activity
│       ├── microstructure.py # Order flow
│       ├── broker.py         # Binance order execution
│       ├── execution_engine.py   # Order mode selection
│       ├── execution_worker.py   # Auto-trade worker
│       ├── risk_engine.py    # Risk calculations
│       ├── self_learning.py  # Adaptive weights
│       ├── portfolio_correlation.py # Correlation check
│       ├── tracker.py        # Trade management
│       └── ...
```

---

## Tech Stack

- **Backend:** Python 3.10+, Flask
- **Data:** Binance Futures API
- **Trading:** python-binance SDK (HMAC-signed)
- **Caching:** Redis
- **Backtesting:** pandas, numpy, pyarrow
- **Deployment:** Railway, Docker

---

## License

MIT License
