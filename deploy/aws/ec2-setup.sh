#!/bin/bash
# ============================================================
# AWS EC2 AUTOMATED DEPLOYMENT SCRIPT
# ============================================================

set -e

echo "🚀 Binance Signal Engine - AWS EC2 Deployment"
echo "=============================================="

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running as root
if [ "$EUID" -eq 0 ]; then 
   echo "${RED}❌ Please run as ubuntu user, not root${NC}"
   exit 1
fi

# Update system
echo "${YELLOW}📦 Updating system...${NC}"
sudo apt update -y && sudo apt upgrade -y

# Install dependencies
echo "${YELLOW}🔧 Installing dependencies...${NC}"
sudo apt install -y \
    python3.11 \
    python3.11-venv \
    python3.11-dev \
    python3-pip \
    git \
    build-essential \
    nginx \
    certbot \
    python3-certbot-nginx \
    htop \
    unzip \
    curl \
    wget

# Install pip for Python 3.11
python3.11 -m ensurepip --upgrade

# Create app directory
echo "${YELLOW}📁 Creating app directory...${NC}"
mkdir -p ~/binance-signal-engine
cd ~/binance-signal-engine

# Clone repository (if not exists)
if [ ! -d ".git" ]; then
    echo "${YELLOW}📥 Cloning repository...${NC}"
    git clone https://github.com/manojkumar12-maker/binance-signal-engine.git .
fi

# Create virtual environment
echo "${YELLOW}🐍 Creating virtual environment...${NC}"
python3.11 -m venv venv
source venv/bin/activate

# Install Python packages
echo "${YELLOW}⬇️ Installing Python packages...${NC}"
pip install --upgrade pip
pip install -r requirements.txt
pip install gunicorn numpy

# Create environment file template
echo "${YELLOW}📝 Creating environment file...${NC}"
cat > .env << EOF
# Server
PORT=8080
HOST=0.0.0.0

# Supabase (update these!)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-service-role-key

# Telegram (update these!)
TELEGRAM_BOT_TOKEN=your-telegram-bot-token
TELEGRAM_CHAT_ID=your-telegram-chat-id

# Binance (optional - for authenticated endpoints)
BINANCE_API_KEY=your-binance-api-key
BINANCE_SECRET_KEY=your-binance-secret-key

# Signal Engine Settings
MIN_CONFIDENCE=75
SNIPER_MODE=true
MAX_SIGNALS_PER_DAY=10
MAX_OPEN_TRADES=3
RISK_PER_TRADE=0.01
MAX_DRAWDOWN=0.05
PAPER_TRADING=true
EOF

echo "${YELLOW}⚠️ IMPORTANT: Edit .env file and add your credentials!${NC}"

# Create systemd service
echo "${YELLOW}⚙️ Creating systemd service...${NC}"
sudo tee /etc/systemd/system/binance-signal.service > /dev/null << EOF
[Unit]
Description=Binance Signal Engine
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/binance-signal-engine
Environment="PATH=/home/ubuntu/binance-signal-engine/venv/bin"
EnvironmentFile=/home/ubuntu/binance-signal-engine/.env
ExecStart=/home/ubuntu/binance-signal-engine/venv/bin/gunicorn -w 2 -b 127.0.0.1:8080 main:app
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=binance-signal

[Install]
WantedBy=multi-user.target
EOF

# Configure Nginx
echo "${YELLOW}🌐 Configuring Nginx...${NC}"
sudo tee /etc/nginx/sites-available/binance-signal > /dev/null << 'EOF'
server {
    listen 80;
    server_name _;

    client_max_body_size 50M;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
        proxy_read_timeout 86400;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8080/api/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    location /health {
        proxy_pass http://127.0.0.1:8080/health;
        access_log off;
    }
}
EOF

# Enable site
sudo ln -sf /etc/nginx/sites-available/binance-signal /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default

# Test Nginx config
sudo nginx -t

# Create update script
echo "${YELLOW}🔄 Creating update script...${NC}"
cat > ~/binance-signal-engine/update.sh << 'EOF'
#!/bin/bash
cd ~/binance-signal-engine
echo "📥 Pulling latest changes..."
git pull origin master
echo "⬇️ Installing dependencies..."
source venv/bin/activate
pip install -r requirements.txt
echo "🔄 Restarting service..."
sudo systemctl restart binance-signal
echo "✅ Updated at $(date)"
EOF
chmod +x ~/binance-signal-engine/update.sh

# Create backup script
echo "${YELLOW}💾 Creating backup script...${NC}"
cat > ~/binance-signal-engine/backup.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="~/backups"
mkdir -p $BACKUP_DIR
DATE=$(date +%Y%m%d_%H%M%S)
# Backup database (if using local)
# Backup code
cd ~/binance-signal-engine
git bundle create $BACKUP_DIR/binance-signal-$DATE.bundle --all
echo "✅ Backup created at $BACKUP_DIR/binance-signal-$DATE.bundle"
EOF
chmod +x ~/binance-signal-engine/backup.sh

# Setup auto-start
echo "${YELLOW}🚀 Enabling auto-start...${NC}"
sudo systemctl daemon-reload
sudo systemctl enable binance-signal
sudo systemctl enable nginx

# Add swap (if needed)
echo "${YELLOW}💾 Adding swap space...${NC}"
if [ ! -f /swapfile ]; then
    sudo fallocate -l 2G /swapfile
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
fi

# Configure firewall
echo "${YELLOW}🔒 Configuring firewall...${NC}"
sudo ufw --force enable
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 8080/tcp

# Start services
echo "${YELLOW}▶️ Starting services...${NC}"
sudo systemctl start nginx
sudo systemctl start binance-signal

# Wait for service to start
sleep 5

# Check status
echo "${YELLOW}📊 Checking status...${NC}"
sudo systemctl status binance-signal --no-pager

# Test health endpoint
echo "${YELLOW}🏥 Testing health endpoint...${NC}"
curl -s http://localhost:8080/health || echo "${RED}⚠️ Health check failed - check logs${NC}"

# Get public IP
PUBLIC_IP=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4)

echo ""
echo "${GREEN}✅ Deployment Complete!${NC}"
echo "${GREEN}==============================================${NC}"
echo ""
echo "🌐 Your app is running at:"
echo "   http://$PUBLIC_IP"
echo "   http://$PUBLIC_IP:8080"
echo ""
echo "📊 Health Check:"
echo "   http://$PUBLIC_IP/health"
echo ""
echo "📁 Important files:"
echo "   - App: ~/binance-signal-engine/"
echo "   - Config: /etc/systemd/system/binance-signal.service"
echo "   - Nginx: /etc/nginx/sites-available/binance-signal"
echo "   - Logs: sudo journalctl -u binance-signal -f"
echo "   - .env: ~/binance-signal-engine/.env"
echo ""
echo "⚠️ IMPORTANT: Don't forget to:"
echo "   1. Edit ~/binance-signal-engine/.env"
echo "   2. Add your Supabase credentials"
echo "   3. Add your Telegram credentials"
echo "   4. Restart: sudo systemctl restart binance-signal"
echo ""
echo "🔄 To update:"
echo "   ./update.sh"
echo ""
echo "📊 To check logs:"
echo "   sudo journalctl -u binance-signal -f"
echo ""
echo "🔄 To restart:"
echo "   sudo systemctl restart binance-signal"
echo ""
