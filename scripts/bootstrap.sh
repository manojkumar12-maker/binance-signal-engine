#!/usr/bin/env bash
set -euo pipefail
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-plugin git
sudo systemctl enable --now docker
if [ ! -d binance-signal-engine ]; then
  git clone https://github.com/manojkumar12-maker/binance-signal-engine.git
fi
cd binance-signal-engine
cp -n .env.example .env
mkdir -p data logs
docker compose up -d --build
echo "Dashboard (private): http://127.0.0.1:8000  (use SSH tunnel)"
