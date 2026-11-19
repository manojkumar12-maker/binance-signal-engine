# Deployment Guide

## Architecture
- One persistent backend service (FastAPI + worker thread).
- SQLite on a persistent disk/volume.
- Lightweight frontend served by backend.

## Steps
1. Copy `.env.example` to `.env` and set values.
2. Set `TRADING_MODE=paper`, disable live flags.
3. Set `ADMIN_USERNAME` and `ADMIN_PASSWORD` securely.
4. Set `DATABASE_URL` to a persistent path (e.g. `sqlite:////app/data/bot.db`).
5. Set `COOKIE_SECURE=true` when using HTTPS.
6. Build and run:
   - Docker: `docker compose up -d --build`
   - Or `python main.py`
7. Verify `GET /api/health` returns ok.
8. Log in with admin credentials and change password.

## Persistent Storage
- Ensure the database directory is on a persistent volume.
- Do not use ephemeral container filesystems for SQLite.

## Fly.io
- Config in `fly.toml`: one machine, persistent volume `data` mounted at `/data`,
  `DATABASE_URL=sqlite:////data/bot.db`, health check `/api/health`.
- Setup (from `engine/`):
  1. `fly launch --no-deploy` (choose the app name; decline creating a second volume).
  2. `fly volumes create data --size 1 --region iad`
  3. `fly secrets set ADMIN_USERNAME=... ADMIN_PASSWORD=... SETTINGS_ENCRYPTION_KEY=<random-hex>`
  4. `fly deploy`
- Keep `SETTINGS_ENCRYPTION_KEY` fixed forever — saved keys are encrypted with it.
- The volume persists across deploys/restarts, so trades, signals and settings are never wiped.