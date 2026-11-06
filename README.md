# BINANCE SIGNAL ENGINE

> **Paper-only** Binance USDT-M Futures signal engine and trading terminal.
> Seven AI agents. Real market data. No fake trades. Live trading disabled by default.

![Tests](https://img.shields.io/badge/tests-139%20passing-brightgreen)
![Mode](https://img.shields.io/badge/mode-PAPER-blue)
![Live Trading](https://img.shields.io/badge/live%20trading-disabled-red)
![Python](https://img.shields.io/badge/python-3.12-blue)

---

## What It Does

- Scans liquid Binance Futures pairs for technical setups (EMA, RSI, MACD, ATR, volume).
- Runs an asset/market risk check (liquidity, volatility, abnormal volume).
- Sizes positions at **0.5% risk per trade** with hard daily-loss and position limits.
- Executes **paper trades only** with realistic fees, slippage, SL/TP monitoring.
- Tracks equity, P&L, drawdown, win rate, and performance analytics.
- Provides a futuristic dark dashboard with a seven-agent command center.
- Ships with auth, admin controls, settings, logging, and Render deployment config.

## Seven Agents

| Agent | Responsibility |
|---|---|
| Scanner | Discovers and ranks trading opportunities |
| Rug Check | Assesses market/asset risk (not on-chain rug detection) |
| Sizer | Percent-based position sizing with exchange filters |
| Executer | Opens and monitors PAPER positions only |
| Logger | Structured event logging with redaction and retention |
| Equity | Equity snapshots, P&L, drawdown, analytics |
| Admin Logs | Administrative actions and system oversight |

## Safety First

- **Default mode: PAPER.** No real orders are submitted.
- Live trading requires multiple independent flags + credentials + a marker file.
- Kill switch persists in SQLite and blocks new execution immediately.
- No martingale, no averaging down, no automatic risk increases.
- Optional Grok AI is disabled by default and never authorizes trades.

## Quick Start

```bash
git clone https://github.com/manojkumar12-maker/binance-signal-engine.git
cd binance-signal-engine
python -m venv .venv
.venv\Scripts\activate   # or source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env   # or cp on Linux/macOS
mkdir -p data logs
python -m pytest -q
python main.py
```

Open `http://127.0.0.1:8000` and log in. Set `ADMIN_USERNAME` and `ADMIN_PASSWORD` in `.env` for first-time setup.

## Architecture

```
main.py -> FastAPI (src/dashboard.py) + worker thread
              |
              +-- Orchestrator (src/orchestrator.py)
              |     Scanner -> Rug Check -> Sizer -> Executer (PAPER)
              |     Logger + Equity + Admin Logs
              +-- SQLite (data/bot.db) on persistent volume
              +-- WebSocket real-time updates
```

## Dashboard

- Overview, Scanner, Rug Check, Sizer, Executer, Open Positions, Logger, Equity, Admin Logs, Settings.
- Seven agent status cards with real state.
- SYSTEM BRAIN panel showing current workflow stage.
- Activity terminal with real backend events.
- TradingView Lightweight Charts for market and equity curves.

## API (selected)

`GET /api/health` · `GET /api/status` · `GET /api/agents` · `GET /api/scanner/results`
`GET /api/rug-check/{symbol}` · `POST /api/sizer/calculate` · `GET /api/paper/account`
`GET /api/equity/analytics` · `GET /api/logs` · `POST /api/system/kill`

Full list in the codebase.

## Deployment (Render)

- Single web service, persistent disk at `/var/data`.
- Start command: `python main.py`
- Health check: `/api/health`
- See `docs/deployment.md`, `docs/operations.md`, `docs/security.md`, `docs/paper-validation.md`.

## Testing

```bash
python -m pytest -q
```

139 tests covering indicators, scanning, risk, paper trading, auth, equity, orchestration, and deployment safety.

## Documentation

- [Deployment](docs/deployment.md)
- [Operations](docs/operations.md)
- [Security](docs/security.md)
- [Paper Validation](docs/paper-validation.md)

## License

MIT. For educational and personal use. Not financial advice.
