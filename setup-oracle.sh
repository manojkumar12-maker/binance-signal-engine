#!/bin/bash

# Oracle Cloud VM Setup Script for Binance Signal Engine
# Run this after SSH into your VM

set -e

echo "🚀 Setting up Binance Signal Engine on Oracle Cloud..."

# Update system
echo "📦 Updating system..."
sudo apt update && sudo apt upgrade -y

# Install dependencies
echo "🔧 Installing dependencies..."
sudo apt install -y python3.11 python3.11-venv python3.11-dev python3-pip git build-essential

# Clone repo
echo "📥 Cloning repository..."
cd ~
if [ ! -d "binance-signal-engine" ]; then
    git clone https://github.com/manojkumar12-maker/binance-signal-engine.git
fi

cd binance-signal-engine

# Create virtual environment
echo "🐍 Creating virtual environment..."
python3.11 -m venv venv
source venv/bin/activate

# Install requirements
echo "⬇️ Installing Python packages..."
pip install --upgrade pip
pip install -r requirements.txt
pip install gunicorn numpy

# Create systemd service
echo "⚙️ Creating system service..."
sudo cp binance-signal.service /etc/systemd/system/binance-signal.service

# Update service with current user
sudo sed -i "s|User=ubuntu|User=$USER|g" /etc/systemd/system/binance-signal.service
sudo sed -i "s|/home/ubuntu|/home/$USER|g" /etc/systemd/system/binance-signal.service

# Reload and enable
echo "🔄 Enabling service..."
sudo systemctl daemon-reload
sudo systemctl enable binance-signal

# Start service
echo "🚀 Starting Binance Signal Engine..."
sudo systemctl start binance-signal

# Check status
echo ""
echo "✅ Setup complete!"
echo ""
echo "📊 Service status:"
sudo systemctl status binance-signal --no-pager

echo ""
echo "📝 Check logs:"
echo "   sudo journalctl -u binance-signal -f"
echo ""
echo "🌐 Your app is running at:"
echo "   http://$(curl -s ifconfig.me):8080"
echo ""
echo "⚠️ IMPORTANT: Don't forget to:"
echo "   1. Edit /etc/systemd/system/binance-signal.service"
echo "   2. Add your TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID"
echo "   3. Run: sudo systemctl restart binance-signal"
echo ""
