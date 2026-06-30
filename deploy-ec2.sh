#!/usr/bin/env bash
set -e

REPO="https://github.com/manojkumar12-maker/binance-signal-engine.git"
BRANCH="master"

echo "=== Installing Docker ==="
sudo apt-get update -qq
sudo apt-get install -y -qq docker.io docker-compose-v2
sudo usermod -aG docker ubuntu

echo "=== Cloning repo ==="
git clone --branch "$BRANCH" "$REPO"
cd binance-signal-engine

echo "=== Creating .env template ==="
cat > .env << 'ENVEOF'
BINANCE_API_KEY=your_key_here
BINANCE_API_SECRET=your_secret_here
TELEGRAM_BOT_TOKEN=your_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
BROKER_ENABLED=true
USE_TESTNET=true
API_KEY=
ENVEOF

echo ""
echo "============================================"
echo "  SETUP COMPLETE"
echo "============================================"
echo ""
echo "  Next steps:"
echo "  1. Edit .env with your API keys:"
echo "     nano binance-signal-engine/.env"
echo ""
echo "  2. Start the app:"
echo "     cd binance-signal-engine && docker compose up -d"
echo ""
echo "  3. View logs:"
echo "     docker compose logs -f"
echo ""
echo "  4. Open dashboard:"
echo "     http://$(curl -s http://checkip.amazonaws.com):8080"
echo "============================================"
