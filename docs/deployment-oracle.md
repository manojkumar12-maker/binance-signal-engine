# Oracle Cloud Free Tier Deployment (Private)

## Instance
- Use Oracle Cloud Always Free ARM (Ampere) or AMD micro instance.
- Open only SSH (22). Do NOT open 8000.

## Install
```bash
sudo apt update && sudo apt install -y docker.io docker-compose-plugin
git clone https://github.com/manojkumar12-maker/binance-signal-engine.git
cd binance-signal-engine
cp .env.example .env
# edit .env: keep LIVE flags false
mkdir -p data logs
docker compose up -d --build
```

## Persistence
- `./data` and `./logs` are mounted volumes. Keep them on the boot volume or a block volume.
- Backup: `bash scripts/backup.sh` (cron daily).

## Restart persistence test
- Record: simulated balance, open position, kill switch, seen signals.
- `docker compose restart` then reboot VM; verify recovered.

## Remote dashboard (private)
- SSH tunnel: `ssh -L 8000:127.0.0.1:8000 ubuntu@<ip>`
- Open http://127.0.0.1:8000 in browser.

## HTTPS (later)
- Add Caddy/Nginx reverse proxy with Let's Encrypt on a domain.
- Keep backend on 127.0.0.1; proxy only.
- Set ADMIN_TOKEN and require X-Admin-Token for /halt /resume.

## 30-day simulation
- Record uptime, stale data, signal counts, fees/slippage, drawdown, recovery.
- Do not treat simulated results as future profitability.

## Live trading
- Remains disabled. Activation requires all flags + credentials + data/LIVE_ACTIVATED marker.
