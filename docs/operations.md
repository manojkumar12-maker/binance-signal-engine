# Operations Guide

## Start / Stop
- Start: `python main.py` or `docker compose up -d`.
- Stop: Ctrl+C or `docker compose down`.

## Health
- `GET /api/health` — backend health.
- `GET /api/monitoring` — disk, DB size, heartbeat, scan freshness.

## Restart Recovery
- Worker resumes monitoring open PAPER positions.
- Kill switch state persists in SQLite.
- No duplicate trades due to signal-seen tracking.

## Logs
- `GET /api/logs` with filters: agent, severity, event_type, symbol, offset, limit.
- `GET /api/logs/summary`.

## Backup / Restore
- Stop app, copy `data/bot.db` to backup, restart.
- Restore by replacing DB file while app stopped.

## Kill Switch
- `POST /api/system/kill` (auth required) or dashboard Emergency Stop.
- Resume via `POST /api/resume` (operator confirmed).

## Troubleshooting
- Stale prices: check Binance connectivity and worker heartbeat.
- No signals: normal if market conditions don't meet rules.
- Auth lockout: wait lockout period or restart (rate limit in memory).