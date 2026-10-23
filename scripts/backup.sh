#!/usr/bin/env bash
set -euo pipefail
TS=$(date +%Y%m%d_%H%M%S)
mkdir -p backups
cp data/bot.db "backups/bot_${TS}.db"
echo "Backup created: backups/bot_${TS}.db"
