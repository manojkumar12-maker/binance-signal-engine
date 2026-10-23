# Binance USDT-M Futures Signal & Trading Bot (Safety-First)

Demo mode by default. Live trading disabled. Simulated starting balance 5 USDT.

## Setup
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
mkdir data
python -m pytest -q
```

## Run dashboard
```bash
python main.py
# http://127.0.0.1:8000/health
```

## Run worker (demo)
```bash
python -m src.worker
```

## Docker
```bash
docker compose up -d --build
```

## Live trading activation (manual, all required)
1. Set TRADING_MODE=live, BROKER_ENABLED=true, AUTO_TRADE=true, LIVE_TRADING_ENABLED=true, USE_TESTNET=false
2. Add real API credentials to .env
3. Ensure IP allowlist and Futures-only permissions, no withdrawals
4. Verify testnet workflow first
5. Run reconciliation and protective-stop tests
6. Restart process; confirm /status shows live_authorized=true

Never enable live trading during testing.