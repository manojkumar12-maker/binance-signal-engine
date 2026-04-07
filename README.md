# Binance Signal Engine

A professional-grade algorithmic trading system for Binance USDT futures that combines Smart Money Concepts (SMC) with quantitative risk management.

---

## Features

### Signal Generation
- **Multi-timeframe alignment** (H4 → H1 → M15)
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
                                                Execution → Risk Engine
                                                          ↓
                                                       Tracking → Self-Learning
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
| `CORRELATION_CHECK` | true | Filter correlated trades |

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
python main.py
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

---

## File Structure

```
binance-signal-engine/
├── main.py                 # Flask server + scanner
├── config.py               # Configuration
├── dashboard.html         # UI dashboard
├── app/
│   └── services/
│       ├── strategy.py       # Signal generation
│       ├── scoring.py      # Confidence calculation
│       ├── structure.py    # Market structure
│       ├── liquidity.py   # Liquidity detection
│       ├── volume.py      # Volume analysis
│       ├── whale.py       # Whale activity
│       ├── microstructure.py  # Order flow
│       ├── execution_engine.py  # Order execution
│       ├── self_learning.py  # Adaptive weights
│       ├── portfolio_correlation.py  # Correlation check
│       ├── tracker.py      # Trade management
│       └── ...
```

---

## Tech Stack

- **Backend:** Python 3.10, Flask
- **Data:** Binance Futures API
- **Caching:** Redis
- **Deployment:** Railway, Docker

---

## License

MIT License