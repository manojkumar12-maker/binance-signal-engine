#!/bin/bash
# ============================================================
# ONE-CLICK AWS EC2 DEPLOYMENT SCRIPT
# ============================================================
# Run this script ON your EC2 instance after SSH login
# It will automatically install everything and start your app
# 
# Usage:
#   ssh -i key.pem ubuntu@YOUR-EC2-IP
#   curl -fsSL https://raw.githubusercontent.com/manojkumar12-maker/binance-signal-engine/master/deploy/aws/one-click-deploy.sh | bash
# ============================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
APP_NAME="binance-signal-engine"
APP_DIR="/home/ubuntu/$APP_NAME"
REPO_URL="https://github.com/manojkumar12-maker/binance-signal-engine.git"
PYTHON_VERSION="3.11"
PORT="8080"

# Logging
LOG_FILE="/var/log/one-click-deploy.log"

# ============================================================
# HELPER FUNCTIONS
# ============================================================

log() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a $LOG_FILE
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" | tee -a $LOG_FILE
}

warn() {
    echo -e "${YELLOW}[WARNING]${NC} $1" | tee -a $LOG_FILE
}

info() {
    echo -e "${BLUE}[INFO]${NC} $1" | tee -a $LOG_FILE
}

# ============================================================
# PRE-FLIGHT CHECKS
# ============================================================

log "🚀 Starting one-click deployment..."
log "This will take about 5-10 minutes..."

# Check if running as root
if [ "$EUID" -eq 0 ]; then 
   error "Please run as ubuntu user, not root"
   exit 1
fi

# Check Ubuntu version
if ! grep -q "Ubuntu" /etc/os-release; then
    warn "This script is designed for Ubuntu. Your OS may not be fully compatible."
fi

# Check internet connection
if ! curl -s --head https://github.com | head -1 | grep -q "200 OK"; then
    error "No internet connection. Please check your network."
    exit 1
fi

# Get public IP
PUBLIC_IP=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || echo "YOUR-EC2-IP")
log "📍 Public IP: $PUBLIC_IP"

# ============================================================
# STEP 1: SYSTEM UPDATE
# ============================================================

log "📦 Step 1/10: Updating system..."
sudo apt-get update -y >> $LOG_FILE 2>&1
sudo apt-get upgrade -y >> $LOG_FILE 2>&1

# ============================================================
# STEP 2: INSTALL DEPENDENCIES
# ============================================================

log "🔧 Step 2/10: Installing dependencies..."
sudo apt-get install -y \
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
    curl \
    wget \
    unzip \
    software-properties-common \
    >> $LOG_FILE 2>&1

# Ensure pip is installed for Python 3.11
python3.11 -m ensurepip --upgrade >> $LOG_FILE 2>&1

# ============================================================
# STEP 3: SETUP APP DIRECTORY
# ============================================================

log "📁 Step 3/10: Setting up application directory..."

if [ -d "$APP_DIR" ]; then
    log "App directory exists. Updating..."
    cd $APP_DIR
    git pull origin master >> $LOG_FILE 2>&1
else
    log "Cloning repository..."
    cd /home/ubuntu
    git clone $REPO_URL $APP_NAME >> $LOG_FILE 2>&1
    cd $APP_DIR
fi

# ============================================================
# STEP 4: CREATE VIRTUAL ENVIRONMENT
# ============================================================

log "🐍 Step 4/10: Creating Python virtual environment..."

if [ ! -d "$APP_DIR/venv" ]; then
    python3.11 -m venv venv
fi

source $APP_DIR/venv/bin/activate

# Upgrade pip
pip install --upgrade pip >> $LOG_FILE 2>&1

# Install requirements
log "⬇️ Installing Python packages..."
pip install -r requirements.txt >> $LOG_FILE 2>&1

# Install additional packages
pip install gunicorn numpy >> $LOG_FILE 2>&1

# ============================================================
# STEP 5: CREATE ENVIRONMENT FILE
# ============================================================

log "📝 Step 5/10: Creating environment file..."

if [ ! -f "$APP_DIR/.env" ]; then
    cat > $APP_DIR/.env << EOF
# ============================================
# BINANCE SIGNAL ENGINE - CONFIGURATION
# ============================================

# Server
PORT=8080
HOST=0.0.0.0

# Supabase (UPDATE THESE!)
# Get from: https://supabase.com/dashboard/project/_/settings/api
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-service-role-key

# Telegram (UPDATE THESE!)
# Get from: https://t.me/BotFather
TELEGRAM_BOT_TOKEN=your-telegram-bot-token
TELEGRAM_CHAT_ID=your-telegram-chat-id

# Binance (optional)
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

    log "⚠️ IMPORTANT: Edit $APP_DIR/.env and add your credentials!"
    log "Run: nano $APP_DIR/.env"
fi

# ============================================================
# STEP 6: CREATE SYSTEMD SERVICE
# ============================================================

log "⚙️ Step 6/10: Creating systemd service..."

sudo tee /etc/systemd/system/$APP_NAME.service > /dev/null << EOF
[Unit]
Description=Binance Signal Engine
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=$APP_DIR
Environment="PATH=$APP_DIR/venv/bin"
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/venv/bin/gunicorn -w 2 -b 127.0.0.1:8080 main:app
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=$APP_NAME

[Install]
WantedBy=multi-user.target
EOF

# ============================================================
# STEP 7: CONFIGURE NGINX
# ============================================================

log "🌐 Step 7/10: Configuring Nginx..."

sudo tee /etc/nginx/sites-available/$APP_NAME > /dev/null << 'EOF'
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
sudo ln -sf /etc/nginx/sites-available/$APP_NAME /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default

# Test Nginx config
sudo nginx -t >> $LOG_FILE 2>&1

# ============================================================
# STEP 8: SETUP FIREWALL & SECURITY
# ============================================================

log "🔒 Step 8/10: Configuring firewall and security..."

# Enable UFW
sudo ufw --force enable >> $LOG_FILE 2>&1

# Allow required ports
sudo ufw allow 22/tcp >> $LOG_FILE 2>&1
sudo ufw allow 80/tcp >> $LOG_FILE 2>&1
sudo ufw allow 443/tcp >> $LOG_FILE 2>&1
sudo ufw allow 8080/tcp >> $LOG_FILE 2>&1

# Add swap space (prevent out of memory)
if [ ! -f /swapfile ]; then
    log "💾 Adding swap space..."
    sudo fallocate -l 2G /swapfile
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
fi

# ============================================================
# STEP 9: START SERVICES
# ============================================================

log "🚀 Step 9/10: Starting services..."

# Reload systemd
sudo systemctl daemon-reload

# Enable services
sudo systemctl enable $APP_NAME
sudo systemctl enable nginx

# Start services
sudo systemctl start nginx
sudo systemctl start $APP_NAME

# Wait for service to start
sleep 5

# ============================================================
# STEP 10: VERIFICATION
# ============================================================

log "✅ Step 10/10: Verifying deployment..."

# Check if service is running
if sudo systemctl is-active --quiet $APP_NAME; then
    log "✅ Signal engine is running!"
else
    error "❌ Signal engine failed to start"
    error "Check logs: sudo journalctl -u $APP_NAME -n 50"
    exit 1
fi

# Test health endpoint
if curl -s http://localhost:8080/health | grep -q "healthy"; then
    log "✅ Health check passed!"
else
    warn "⚠️ Health check failed - app may still be starting"
fi

# ============================================================
# CREATE HELPER SCRIPTS
# ============================================================

# Update script
sudo tee /usr/local/bin/update-signal-engine > /dev/null << 'EOF'
#!/bin/bash
cd /home/ubuntu/binance-signal-engine
echo "📥 Pulling latest changes..."
git pull origin master
echo "⬇️ Installing dependencies..."
source venv/bin/activate
pip install -r requirements.txt
echo "🔄 Restarting service..."
sudo systemctl restart binance-signal
echo "✅ Updated at $(date)"
EOF
sudo chmod +x /usr/local/bin/update-signal-engine

# Status script
sudo tee /usr/local/bin/signal-status > /dev/null << 'EOF'
#!/bin/bash
echo "📊 Signal Engine Status:"
sudo systemctl status binance-signal --no-pager
echo ""
echo "📈 Recent logs:"
sudo journalctl -u binance-signal -n 20 --no-pager
EOF
sudo chmod +x /usr/local/bin/signal-status

# Logs script
sudo tee /usr/local/bin/signal-logs > /dev/null << 'EOF'
#!/bin/bash
sudo journalctl -u binance-signal -f
EOF
sudo chmod +x /usr/local/bin/signal-logs

# ============================================================
# COMPLETION
# ============================================================

log ""
log "${GREEN}🎉 DEPLOYMENT COMPLETE!${NC}"
log "${GREEN}==============================================${NC}"
log ""
log "🌐 Your app is running at:"
log "   http://$PUBLIC_IP"
log "   http://$PUBLIC_IP:8080"
log ""
log "📊 Health Check:"
log "   http://$PUBLIC_IP/health"
log ""
log "⚠️ IMPORTANT: You MUST do this:"
log "   1. Edit: nano $APP_DIR/.env"
log "   2. Add: SUPABASE_URL, SUPABASE_KEY"
log "   3. Add: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID"
log "   4. Restart: sudo systemctl restart $APP_NAME"
log ""
log "🔄 Helper commands:"
log "   update-signal-engine  - Update app from GitHub"
log "   signal-status         - Check status"
log "   signal-logs           - View logs"
log ""
log "📁 Important locations:"
log "   App: $APP_DIR"
log "   Logs: sudo journalctl -u $APP_NAME -f"
log "   Config: /etc/systemd/system/$APP_NAME.service"
log "   Nginx: /etc/nginx/sites-available/$APP_NAME"
log ""
log "🔧 Useful commands:"
log "   sudo systemctl restart $APP_NAME"
log "   sudo systemctl status $APP_NAME"
log "   sudo nginx -t"
log "   sudo systemctl restart nginx"
log ""
log "${YELLOW}📝 Next steps:${NC}"
log "   1. Edit .env file with your credentials"
log "   2. Restart the service"
log "   3. Test: curl http://$PUBLIC_IP/health"
log "   4. Update dashboard.html API URL to: http://$PUBLIC_IP:8080/api"
log ""
log "${GREEN}✅ Ready to use!${NC}"
