# ORACLE CLOUD FREE TIER DEPLOYMENT GUIDE

## What You Get (ALWAYS FREE - FOREVER)

- **4 ARM CPU cores** (Ampere A1)
- **24 GB RAM** total
- **200 GB storage**
- **10 TB/month** egress
- **Always Free** - never expires, no credit card needed
- **Ubuntu 22.04** VM
- **Public IP** (static)
- **Custom domain** support

---

## STEP 1: Create Oracle Cloud Account

### 1. Sign Up
```
1. Go to: https://www.oracle.com/cloud/free/
2. Click "Start for Free"
3. Create Oracle Account (or use existing)
4. Verify email
5. Enter home address (any real address)
6. Enter credit card (for verification, NOT charged)
7. Complete signup
```

**IMPORTANT:**
- Use real information (they verify)
- Credit card is for verification only (₹100 hold, released immediately)
- You get $300 credits for 30 days (trial) + Always Free resources forever

---

## STEP 2: Create VM Instance

### 1. Log into Console
```
https://cloud.oracle.com
→ Compute → Instances
```

### 2. Create Instance
```
Click "Create Instance"

Name: binance-signal-engine
Availability Domain: AD-1 (any)
Image: Canonical Ubuntu 22.04 (Recommended)
Shape: Ampere (ARM) - VM.Standard.A1.Flex
  - OCPUs: 2 (up to 4 free)
  - Memory: 12 GB (up to 24 GB free)
  - Boot Volume: 50 GB (up to 200 GB free)

Networking:
  - Create new VCN (or use existing)
  - Assign public IP: YES

Add SSH Keys:
  - Generate new key pair (or upload your own)
  - Download private key (.key file)
  - SAVE IT - you cannot download again

Click "Create"
```

**Wait 2-3 minutes for instance to start.**

---

## STEP 3: Configure Networking (Open Port 8080)

### 1. Go to Security Lists
```
Networking → Virtual Cloud Networks → Your VCN
→ Security Lists → Default Security List
```

### 2. Add Ingress Rule
```
Click "Add Ingress Rule"

Stateless: No
Source Type: CIDR
Source CIDR: 0.0.0.0/0 (or your IP/32 for security)
IP Protocol: TCP
Destination Port Range: 8080
Description: Signal Engine Port

Click "Add Ingress Rule"
```

### 3. (Optional) Add HTTPS (443) if using SSL later
```
Same as above but port 443
```

---

## STEP 4: Connect to Your VM

### 1. Get Public IP
```
Compute → Instances → Your Instance
→ Copy Public IP Address (e.g., 152.67.123.45)
```

### 2. SSH into VM
```bash
# On Windows (PowerShell or Git Bash):
ssh -i ~/.ssh/your-key.key ubuntu@152.67.123.45

# On Mac/Linux:
chmod 600 ~/.ssh/your-key.key
ssh -i ~/.ssh/your-key.key ubuntu@152.67.123.45
```

**Replace:**
- `~/.ssh/your-key.key` with your downloaded key path
- `152.67.123.45` with your actual public IP

---

## STEP 5: Install Dependencies

### 1. Update System
```bash
sudo apt update && sudo apt upgrade -y
```

### 2. Install Python & Dependencies
```bash
# Install Python 3.11
sudo apt install -y python3.11 python3.11-venv python3.11-dev python3-pip

# Install git
sudo apt install -y git

# Install build tools
sudo apt install -y build-essential libssl-dev
```

### 3. Clone Your Repo
```bash
# Go to home directory
cd ~

# Clone repo
git clone https://github.com/manojkumar12-maker/binance-signal-engine.git

# Enter directory
cd binance-signal-engine
```

### 4. Create Virtual Environment
```bash
# Create venv
python3.11 -m venv venv

# Activate
source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Install gunicorn
pip install gunicorn

# Install numpy (for new modules)
pip install numpy
```

---

## STEP 6: Configure Environment Variables

### 1. Create .env file
```bash
nano ~/binance-signal-engine/.env
```

### 2. Add your variables
```
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
PORT=8080
```

### 3. Save (Ctrl+O, Enter, Ctrl+X)

---

## STEP 7: Test the App

### 1. Run Manually
```bash
cd ~/binance-signal-engine
source venv/bin/activate

# Test with Flask development server
python main.py

# Or test with gunicorn
gunicorn -w 1 -b 0.0.0.0:8080 main:app
```

### 2. Check if it's running
```bash
# In another terminal window, SSH again:
curl http://localhost:8080/health

# Should return: {"status": "healthy"}
```

### 3. Stop test
```bash
# Press Ctrl+C to stop
```

---

## STEP 8: Create Systemd Service (Auto-Start)

### 1. Create Service File
```bash
sudo nano /etc/systemd/system/binance-signal.service
```

### 2. Paste this configuration
```ini
[Unit]
Description=Binance Signal Engine
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/binance-signal-engine
Environment="PATH=/home/ubuntu/binance-signal-engine/venv/bin"
Environment="TELEGRAM_BOT_TOKEN=your_bot_token_here"
Environment="TELEGRAM_CHAT_ID=your_chat_id_here"
Environment="PORT=8080"
ExecStart=/home/ubuntu/binance-signal-engine/venv/bin/gunicorn -w 1 -b 0.0.0.0:8080 main:app
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Replace:**
- `your_bot_token_here` with actual token
- `your_chat_id_here` with actual chat ID

### 3. Save and Enable
```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable service (auto-start on boot)
sudo systemctl enable binance-signal

# Start service
sudo systemctl start binance-signal

# Check status
sudo systemctl status binance-signal
```

### 4. Common Commands
```bash
# Start
sudo systemctl start binance-signal

# Stop
sudo systemctl stop binance-signal

# Restart
sudo systemctl restart binance-signal

# Check logs
sudo journalctl -u binance-signal -f

# Check logs (last 50 lines)
sudo journalctl -u binance-signal -n 50
```

---

## STEP 9: Access Your App

### 1. Get Your Public URL
```
http://152.67.123.45:8080

# Health check:
http://152.67.123.45:8080/health

# Dashboard:
http://152.67.123.45:8080/dashboard

# API:
http://152.67.123.45:8080/api/signals
```

**Replace** `152.67.123.45` with your actual public IP.

---

## STEP 10: (Optional) Add Custom Domain

### 1. Buy Domain (or use free subdomain)
```
Free options:
- DuckDNS: https://www.duckdns.org
- No-IP: https://www.noip.com
- Freenom: https://freenom.com
```

### 2. Point Domain to IP
```
Create A record:
Host: @
Points to: 152.67.123.45 (your IP)
```

### 3. Setup SSL with Nginx (Free HTTPS)
```bash
# Install nginx
sudo apt install -y nginx

# Install certbot
sudo apt install -y certbot python3-certbot-nginx

# Configure nginx
sudo nano /etc/nginx/sites-available/binance-signal
```

Paste:
```nginx
server {
    listen 80;
    server_name yourdomain.com;

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
    }
}
```

```bash
# Enable site
sudo ln -s /etc/nginx/sites-available/binance-signal /etc/nginx/sites-enabled/

# Test nginx config
sudo nginx -t

# Restart nginx
sudo systemctl restart nginx

# Get SSL certificate
sudo certbot --nginx -d yourdomain.com

# Auto-renew SSL
sudo certbot renew --dry-run
```

Now your app is at `https://yourdomain.com` with free SSL!

---

## STEP 11: Setup Auto-Updates

### 1. Create Update Script
```bash
nano ~/binance-signal-engine/update.sh
```

Paste:
```bash
#!/bin/bash
cd ~/binance-signal-engine
git pull origin master
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart binance-signal
echo "Updated and restarted at $(date)"
```

### 2. Make Executable
```bash
chmod +x ~/binance-signal-engine/update.sh
```

### 3. (Optional) Auto-update daily
```bash
# Add to crontab
crontab -e

# Add line:
0 3 * * * ~/binance-signal-engine/update.sh >> ~/binance-signal-engine/update.log 2>&1
```

This updates at 3 AM daily.

---

## STEP 12: Monitoring

### 1. Check System Resources
```bash
# CPU/Memory
htop

# Disk usage
df -h

# Memory usage
free -h
```

### 2. Check App Logs
```bash
# Real-time logs
sudo journalctl -u binance-signal -f

# Last 100 lines
sudo journalctl -u binance-signal -n 100
```

### 3. Restart if Issues
```bash
# Full restart
sudo systemctl restart binance-signal

# Or reboot VM
sudo reboot
```

---

## TROUBLESHOOTING

### 1. Port 8080 Not Accessible
```bash
# Check firewall
sudo iptables -L

# Open port 8080
sudo iptables -I INPUT -p tcp --dport 8080 -j ACCEPT
sudo iptables-save
```

### 2. App Not Starting
```bash
# Check logs
sudo journalctl -u binance-signal -n 50

# Check if port is in use
sudo lsof -i :8080

# Kill process if needed
sudo kill -9 <PID>
```

### 3. Out of Memory
```bash
# Check memory
free -h

# Add swap space
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# Make permanent
sudo nano /etc/fstab
# Add: /swapfile none swap sw 0 0
```

### 4. Git Permission Issues
```bash
# Fix permissions
sudo chown -R ubuntu:ubuntu ~/binance-signal-engine
```

---

## BACKUP YOUR VM

### 1. Create Boot Volume Backup
```
Oracle Console → Block Storage → Boot Volumes
→ Your Boot Volume → Create Backup
```

### 2. Or Clone VM
```
Compute → Instances → Your Instance
→ Actions → Create Instance Configuration
```

---

## SUMMARY

**What you now have:**
- ✅ Free VM (4 CPU, 24GB RAM, 200GB storage)
- ✅ Always running (24/7)
- ✅ Auto-start on boot
- ✅ Public IP access
- ✅ HTTPS (with custom domain)
- ✅ Auto-update capability
- ✅ Complete monitoring

**Your app URL:**
```
http://YOUR_IP:8080
```

**Cost:** ₹0 forever (Always Free tier)

**Next steps:**
1. Configure Telegram bot
2. Test signals
3. Monitor performance
4. Scale up if needed (paid tier available)

---

## QUICK REFERENCE

```bash
# SSH into VM
ssh -i key.pem ubuntu@IP

# View logs
sudo journalctl -u binance-signal -f

# Restart app
sudo systemctl restart binance-signal

# Update app
cd ~/binance-signal-engine && git pull && pip install -r requirements.txt && sudo systemctl restart binance-signal

# Check status
sudo systemctl status binance-signal

# Reboot VM
sudo reboot
```

---

## SUPPORT

**Oracle Cloud:**
- Docs: https://docs.oracle.com/en-us/iaas/Content/home.htm
- Community: https://community.oracle.com

**Your App:**
- Check logs: `sudo journalctl -u binance-signal -f`
- Restart: `sudo systemctl restart binance-signal`
- Health: `curl http://localhost:8080/health`
