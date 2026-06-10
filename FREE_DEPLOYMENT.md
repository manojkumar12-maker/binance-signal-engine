# FREE BACKEND DEPLOYMENT GUIDE

## Option 1: Render.com (RECOMMENDED - FREE FOREVER)

### 1. Deploy Steps
```bash
# 1. Go to https://dashboard.render.com
# 2. Sign up with GitHub
# 3. Click "New Web Service"
# 4. Connect your GitHub repo
# 5. Select the repo
# 6. Use these settings:
```

### 2. Settings
```
Name: binance-signal-engine
Environment: Python 3
Build Command: pip install -r requirements.txt
Start Command: gunicorn -w 1 main:app --bind 0.0.0.0:$PORT
Plan: Free
```

### 3. Environment Variables
```
PORT=8080
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id
```

**PROS:**
- Always free (24/7)
- 512MB RAM
- 750 hours/month
- GitHub auto-deploy
- Custom domain
- HTTPS by default

**CONS:**
- Spins down after 15 min inactivity (wakes up in 30 sec)
- 512MB RAM limit

---

## Option 2: Railway (Free Tier)

### 1. Deploy Steps
```bash
# 1. Go to https://railway.app
# 2. Sign up with GitHub
# 3. Click "New Project"
# 4. Deploy from GitHub repo
# 5. Your railway.json already exists
```

**PROS:**
- Easy deployment
- Good for testing

**CONS:**
- Free tier limited (sleep after inactivity)
- Need credit card for verification

---

## Option 3: Oracle Cloud (ALWAYS FREE - FOREVER)

### 1. Setup
```bash
# 1. Sign up at https://www.oracle.com/cloud/free/
# 2. Get 2 free VMs forever (ARM64)
# 3. 4 CPUs, 24GB RAM total
# 4. Deploy your app

# SSH into your instance
git clone https://github.com/manojkumar12-maker/binance-signal-engine
cd binance-signal-engine
pip install -r requirements.txt
pip install gunicorn

# Run with gunicorn
gunicorn -w 2 -b 0.0.0.0:8080 main:app

# Or use systemd to keep it running
```

**PROS:**
- TRULY FREE forever (no limits)
- 24GB RAM total
- Always available
- No spin down

**CONS:**
- Requires setup
- No auto-deploy from GitHub

---

## Option 4: PythonAnywhere (3 Months Free)

### 1. Setup
```bash
# 1. Sign up at https://www.pythonanywhere.com
# 2. Upload code via GitHub or files
# 3. Create virtualenv
# 4. Install requirements
# 5. Configure WSGI file
```

**PROS:**
- Simple for Python apps
- Free for 3 months

**CONS:**
- Limited after 3 months
- Daily reboot

---

## Option 5: Fly.io (Free Tier)

### 1. Deploy
```bash
# Install flyctl
# 1. Sign up at https://fly.io
# 2. Install flyctl
# 3. Deploy:

flyctl launch
flyctl deploy
```

**PROS:**
- Free tier available
- Docker-based

**CONS:**
- Requires credit card
- Limited free hours

---

## QUICK START: Deploy to Render.com

### Step 1: Create render.yaml
```yaml
services:
  - type: web
    name: binance-signal-engine
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: gunicorn -w 1 main:app --bind 0.0.0.0:$PORT
    envVars:
      - key: PORT
        value: 8080
      - key: PYTHON_VERSION
        value: 3.11.0
```

### Step 2: Push to GitHub
```bash
git add render.yaml
git commit -m "Add Render deployment config"
git push origin master
```

### Step 3: Connect to Render
```
1. Go to https://render.com
2. Click "New Web Service"
3. Connect GitHub repo
4. Select your repo
5. Render auto-detects render.yaml
6. Click "Create Web Service"
```

### Step 4: Add Environment Variables
```
Go to dashboard → Settings → Environment Variables

Add:
TELEGRAM_BOT_TOKEN=your_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
```

---

## MONITORING: Keep it Alive

For free tiers that spin down, use:

### 1. UptimeRobot (Free)
```
https://uptimerobot.com

- Monitor every 5 minutes
- Keeps Render free tier awake
- Free forever
```

### 2. Cron-job.org (Free)
```
https://cron-job.org

- Ping your endpoint every 10 minutes
- Prevents spin down
```

### 3. StatusCake (Free)
```
https://www.statuscake.com

- Free monitoring
- 10-minute intervals
```

---

## CHOOSING THE BEST OPTION

| Platform | Free Forever | Always On | RAM | Ease |
|----------|-------------|-----------|-----|------|
| **Render** | Yes | 30-sec wake | 512MB | Easy |
| **Oracle Cloud** | Yes | Yes | 24GB | Hard |
| **Railway** | Limited | No | 512MB | Easy |
| **PythonAnywhere** | 3 months | No | 512MB | Easy |
| **Fly.io** | Limited | No | 256MB | Medium |

**RECOMMENDATION:**
1. Use **Render.com** for quick deployment (free forever)
2. Use **UptimeRobot** to keep it awake
3. When you need more power, migrate to **Oracle Cloud**

---

## DEPLOYMENT FILES

I've created `render.yaml` for you. Just:
1. Push to GitHub
2. Connect to Render
3. Done

Your app will be live at: `https://binance-signal-engine.onrender.com`
