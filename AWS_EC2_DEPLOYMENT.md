# AWS EC2 DEPLOYMENT GUIDE

## What You Get
- **t2.micro** (free tier 12 months) or **t3.micro** ($8.50/month)
- **Ubuntu 22.04** LTS
- **Elastic IP** (static IP)
- **24/7 uptime**
- **Scalable** (upgrade anytime)

## Prerequisites
1. AWS account (https://aws.amazon.com)
2. Credit card (for verification)
3. GitHub repo access

---

## STEP 1: Create AWS Account

1. Go to https://aws.amazon.com
2. Click "Create AWS Account"
3. Enter email, password, account name
4. Add contact information
5. Add credit card (may charge ₹1-2 for verification, refunded)
6. Verify identity via phone
7. Select support plan (Basic is free)
8. Complete signup

**Free tier includes:**
- 750 hours/month of t2.micro (enough for 1 instance running 24/7)
- 30 GB storage
- 15 GB bandwidth
- 12 months free

---

## STEP 2: Launch EC2 Instance

### 1. Go to EC2 Console
```
https://console.aws.amazon.com/ec2
```

### 2. Launch Instance
```
Click "Launch Instance"

Name: binance-signal-engine
Application and OS: Ubuntu Server 22.04 LTS (Free tier eligible)
Instance type: t2.micro (Free tier eligible)

Key pair:
  - Click "Create new key pair"
  - Name: binance-signal-key
  - Format: .pem (for Mac/Linux) or .ppk (for Windows)
  - Download and SAVE IT

Network settings:
  - VPC: Default
  - Subnet: Any availability zone
  - Auto-assign public IP: Enable
  - Firewall: Create security group
  - Security group name: binance-signal-sg
  - Description: Allow HTTP and SSH
  
  Inbound rules:
  - SSH (22) from My IP (or 0.0.0.0/0 for any)
  - HTTP (80) from 0.0.0.0/0
  - Custom TCP (8080) from 0.0.0.0/0
  - HTTPS (443) from 0.0.0.0/0

Storage:
  - 1x 30 GB gp2 (Free tier eligible)

Advanced details:
  - User data (optional, we'll do manually)

Click "Launch Instance"
```

### 3. Allocate Elastic IP (Static IP)
```
Left sidebar → Network & Security → Elastic IPs
Click "Allocate Elastic IP address"
  - Network border group: default
  - Tags: Name = binance-signal-ip
Click "Allocate"

Select the IP → Actions → Associate Elastic IP address
  - Instance: binance-signal-engine
  - Private IP: (auto-selected)
Click "Associate"
```

**Note:** Elastic IP is free when attached to running instance. If instance is stopped, you pay $0.005/hour.

---

## STEP 3: Connect to Instance

### 1. Get Connection Details
```
Instances → binance-signal-engine
Copy: Public IPv4 address (e.g., 3.85.123.45)
```

### 2. SSH into Instance

**Mac/Linux:**
```bash
chmod 400 ~/Downloads/binance-signal-key.pem
ssh -i ~/Downloads/binance-signal-key.pem ubuntu@3.85.123.45
```

**Windows (PowerShell):**
```powershell
# If using .pem
ssh -i "C:\Users\YourName\Downloads\binance-signal-key.pem" ubuntu@3.85.123.45

# If using .ppk (with PuTTY)
# Use PuTTY with the .ppk file
```

**Replace** `3.85.123.45` with your actual Elastic IP.

---

## STEP 4: Setup Server

### 1. Update System
```bash
sudo apt update && sudo apt upgrade -y
```

### 2. Install Python & Dependencies
```bash
sudo apt install -y python3.11 python3.11-venv python3.11-dev python3-pip git build-essential nginx

# Install pip for Python 3.11
python3.11 -m ensurepip --upgrade
```

### 3. Clone Repository
```bash
cd ~
git clone https://github.com/manojkumar12-maker/binance-signal-engine.git
cd binance-signal-engine
```

### 4. Create Virtual Environment
```bash
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install gunicorn numpy
```

### 5. Create Environment File
```bash
nano .env
```

Paste:
```
PORT=8080
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-supabase-service-key
AWS_REGION=us-east-1
```

Save: Ctrl+O, Enter, Ctrl+X

---

## STEP 5: Configure Nginx (Reverse Proxy)

### 1. Create Nginx Config
```bash
sudo nano /etc/nginx/sites-available/binance-signal
```

Paste:
```nginx
server {
    listen 80;
    server_name _;  # Accept any domain/IP

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

    location /api/ {
        proxy_pass http://127.0.0.1:8080/api/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 2. Enable Site
```bash
sudo ln -s /etc/nginx/sites-available/binance-signal /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx
```

---

## STEP 6: Setup Systemd Service

### 1. Create Service File
```bash
sudo nano /etc/systemd/system/binance-signal.service
```

Paste:
```ini
[Unit]
Description=Binance Signal Engine
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/binance-signal-engine
Environment="PATH=/home/ubuntu/binance-signal-engine/venv/bin"
Environment="PORT=8080"
Environment="TELEGRAM_BOT_TOKEN=your_telegram_bot_token"
Environment="TELEGRAM_CHAT_ID=your_telegram_chat_id"
Environment="SUPABASE_URL=https://your-project.supabase.co"
Environment="SUPABASE_KEY=your-supabase-service-key"
ExecStart=/home/ubuntu/binance-signal-engine/venv/bin/gunicorn -w 2 -b 127.0.0.1:8080 main:app
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### 2. Enable and Start Service
```bash
sudo systemctl daemon-reload
sudo systemctl enable binance-signal
sudo systemctl start binance-signal
```

### 3. Check Status
```bash
sudo systemctl status binance-signal
```

---

## STEP 7: Setup SSL (HTTPS)

### 1. Install Certbot
```bash
sudo apt install -y certbot python3-certbot-nginx
```

### 2. Get SSL Certificate
```bash
# If you have a domain
sudo certbot --nginx -d yourdomain.com

# If using IP only (self-signed, not recommended for production)
# Or use Cloudflare for free SSL
```

### 3. Auto-renew
```bash
sudo certbot renew --dry-run
```

**Note:** For free SSL without a domain, use Cloudflare:
1. Get free domain (freenom.com)
2. Point to Cloudflare
3. Cloudflare provides free SSL

---

## STEP 8: Test Everything

### 1. Check Health
```bash
curl http://localhost/health
# Should return: {"status": "healthy"}
```

### 2. Check API
```bash
curl http://localhost/api/signals
# Should return signals
```

### 3. Check from Internet
```bash
# From your local machine
curl http://YOUR_ELASTIC_IP/health
```

---

## STEP 9: Setup Monitoring

### 1. Install CloudWatch Agent (optional)
```bash
sudo apt install -y amazon-cloudwatch-agent
```

### 2. UptimeRobot (Free)
```
https://uptimerobot.com

1. Sign up
2. Add monitor:
   - Type: HTTP(s)
   - URL: http://YOUR_ELASTIC_IP/health
   - Interval: 5 minutes
   - Alert: Email
```

### 3. Setup Alerts
```bash
# Install AWS CLI
sudo apt install -y awscli

# Configure
aws configure
```

---

## STEP 10: Auto-Update Script

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
echo "Updated at $(date)"
```

### 2. Make Executable
```bash
chmod +x ~/binance-signal-engine/update.sh
```

### 3. Auto-update (optional)
```bash
crontab -e
# Add: 0 3 * * * ~/binance-signal-engine/update.sh >> ~/update.log 2>&1
```

---

## SECURITY BEST PRACTICES

### 1. Update Security Group
```
Only allow:
- SSH (22): Your IP only (not 0.0.0.0/0)
- HTTP (80): 0.0.0.0/0
- HTTPS (443): 0.0.0.0/0
- Custom (8080): Your frontend IP only
```

### 2. Enable Firewall
```bash
sudo ufw enable
sudo ufw allow 22
sudo ufw allow 80
sudo ufw allow 443
sudo ufw allow 8080
sudo ufw status
```

### 3. Disable Root Login
```bash
sudo nano /etc/ssh/sshd_config

# Change:
PermitRootLogin no
PasswordAuthentication no

sudo systemctl restart sshd
```

### 4. Auto Security Updates
```bash
sudo apt install -y unattended-upgrades
sudo dpkg-reconfigure unattended-upgrades
# Select: Yes
```

---

## TROUBLESHOOTING

### 1. Can't SSH
```bash
# Check instance is running
# Check security group allows SSH (22)
# Check key file permissions (chmod 400)
# Check you're using correct user (ubuntu)
```

### 2. App Not Running
```bash
# Check logs
sudo journalctl -u binance-signal -f

# Check if port is in use
sudo lsof -i :8080

# Restart
sudo systemctl restart binance-signal
```

### 3. Nginx Error
```bash
# Test config
sudo nginx -t

# Check error logs
sudo tail -f /var/log/nginx/error.log

# Restart nginx
sudo systemctl restart nginx
```

### 4. Out of Memory
```bash
# Check memory
free -h

# Add swap
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# Make permanent
sudo nano /etc/fstab
# Add: /swapfile none swap sw 0 0
```

---

## COSTS

### Free Tier (12 months)
- t2.micro: Free
- 30 GB storage: Free
- 15 GB bandwidth: Free
- **Total: $0**

### After 12 Months (or if you want more power)
- t3.micro: $8.50/month
- 30 GB storage: $3.60/month
- Bandwidth: $0.09/GB
- **Total: ~$12/month**

### Scaling Up
- t3.small (2 CPU, 2GB): $16.60/month
- t3.medium (2 CPU, 4GB): $33.20/month
- t3.large (2 CPU, 8GB): $66.40/month

---

## BACKUP & RECOVERY

### 1. Create AMI (Image)
```
EC2 → Instances → Your Instance
→ Actions → Image and templates → Create image
Name: binance-signal-backup
Description: Backup before update
Click: Create Image
```

### 2. Snapshot Volumes
```
EC2 → Volumes → Your Volume
→ Actions → Create Snapshot
Description: Daily backup
```

### 3. Automated Backups
```
AWS Backup → Create Backup Plan
Frequency: Daily
Retention: 7 days
```

---

## USEFUL COMMANDS

```bash
# SSH
ssh -i key.pem ubuntu@YOUR_IP

# View logs
sudo journalctl -u binance-signal -f

# Restart app
sudo systemctl restart binance-signal

# Check status
sudo systemctl status binance-signal

# Update app
cd ~/binance-signal-engine && git pull && pip install -r requirements.txt && sudo systemctl restart binance-signal

# Check resources
htop
df -h
free -h

# Restart server
sudo reboot

# Check nginx
sudo nginx -t
sudo systemctl restart nginx
```

---

## QUICK REFERENCE

| Task | Command |
|------|---------|
| SSH | `ssh -i key.pem ubuntu@IP` |
| Logs | `sudo journalctl -u binance-signal -f` |
| Restart | `sudo systemctl restart binance-signal` |
| Status | `sudo systemctl status binance-signal` |
| Update | `git pull && pip install -r requirements.txt && sudo systemctl restart binance-signal` |
| Reboot | `sudo reboot` |
| Nginx test | `sudo nginx -t` |
| Check port | `sudo lsof -i :8080` |

---

## NEXT STEPS

1. ✅ AWS account created
2. ✅ EC2 instance launched
3. ✅ Elastic IP allocated
4. ✅ Server configured
5. ✅ App deployed
6. ✅ SSL enabled (optional)
7. ✅ Monitoring setup
8. 🔄 Connect to Supabase
9. 🔄 Deploy frontend to Vercel
10. 🔄 Test end-to-end

**Your app is live at:** `http://YOUR_ELASTIC_IP`

---

## SUPPORT

- **AWS Console**: https://console.aws.amazon.com
- **AWS Docs**: https://docs.aws.amazon.com/ec2
- **AWS Pricing**: https://aws.amazon.com/ec2/pricing
- **Your Logs**: `sudo journalctl -u binance-signal -f`

**Happy trading! 🚀**
