# COMPLETE DEPLOYMENT CHECKLIST

## Phase 1: SUPABASE DATABASE (5 minutes)

### Step 1: Create Project
- [ ] Go to https://supabase.com
- [ ] Sign up with GitHub
- [ ] Click "New Project"
- [ ] Name: `binance-signal-engine`
- [ ] Database password: Save this!
- [ ] Region: Mumbai (for India) or closest to you
- [ ] Wait 2-3 minutes for setup

### Step 2: Get Credentials
- [ ] Go to Project Settings → API
- [ ] Copy URL: `https://xyz.supabase.co`
- [ ] Copy `anon public` key (for frontend)
- [ ] Copy `service_role` key (for backend - KEEP SECRET!)
- [ ] Save to `.env` file

### Step 3: Create Tables
- [ ] Go to SQL Editor → New Query
- [ ] Copy `deploy/supabase/schema.sql` from this repo
- [ ] Paste and click Run
- [ ] Verify tables created (Table Editor)

### Step 4: Enable Realtime
- [ ] Database → Replication
- [ ] Turn on "Realtime" for: signals, trades, analytics

### Step 5: Test
- [ ] SQL Editor: `SELECT * FROM signals;`
- [ ] Should return empty table (no errors)

**Status: ✅ DATABASE READY**

---

## Phase 2: AWS EC2 (15 minutes)

### Step 1: Create AWS Account
- [ ] Go to https://aws.amazon.com
- [ ] Create account
- [ ] Add credit card (verification only, ₹1-2 hold)
- [ ] Complete identity verification
- [ ] Select Basic support plan (free)

### Step 2: Launch EC2 Instance
- [ ] Go to EC2 Console
- [ ] Click "Launch Instance"
- [ ] Name: `binance-signal-engine`
- [ ] OS: Ubuntu Server 22.04 LTS
- [ ] Instance type: t2.micro (Free tier)
- [ ] Create key pair: `binance-signal-key.pem`
- [ ] Download key (SAVE IT!)
- [ ] Security group: Allow SSH (22), HTTP (80), HTTPS (443), Custom (8080)
- [ ] Storage: 30 GB
- [ ] Click Launch

### Step 3: Allocate Elastic IP
- [ ] EC2 → Elastic IPs → Allocate
- [ ] Associate with instance
- [ ] Copy IP address

### Step 4: Connect & Setup
```bash
# SSH into instance
ssh -i binance-signal-key.pem ubuntu@YOUR_IP

# Run setup script
curl -fsSL https://raw.githubusercontent.com/manojkumar12-maker/binance-signal-engine/master/deploy/ec2-setup.sh | bash

# Or manually:
git clone https://github.com/manojkumar12-maker/binance-signal-engine.git
cd binance-signal-engine
./setup-oracle.sh  # or AWS equivalent
```

### Step 5: Configure Environment
- [ ] `nano .env`
- [ ] Add Supabase credentials
- [ ] Add Telegram credentials
- [ ] Save

### Step 6: Start Service
```bash
sudo systemctl start binance-signal
sudo systemctl status binance-signal
```

### Step 7: Test
```bash
curl http://localhost:8080/health
# Should return {"status": "healthy"}
```

**Status: ✅ BACKEND READY**

---

## Phase 3: VERCEL FRONTEND (2 minutes)

### Step 1: Deploy
- [ ] Go to https://vercel.com
- [ ] Sign up with GitHub
- [ ] Click "Add New Project"
- [ ] Import your GitHub repo
- [ ] Framework: Next.js
- [ ] Click Deploy
- [ ] Wait 30 seconds

### Step 2: Add Environment Variables
- [ ] Project Settings → Environment Variables
- [ ] Add:
  - `NEXT_PUBLIC_SUPABASE_URL`
  - `NEXT_PUBLIC_SUPABASE_ANON_KEY`
  - `SIGNAL_ENGINE_URL`
- [ ] Click Save

### Step 3: Configure Domain
- [ ] Project Settings → Domains
- [ ] Add custom domain (optional)
- [ ] Or use default: `https://your-project.vercel.app`

### Step 4: Test
- [ ] Open URL in browser
- [ ] Should see dashboard
- [ ] Check console for errors

**Status: ✅ FRONTEND READY**

---

## Phase 4: INTEGRATION TESTING (10 minutes)

### Step 1: End-to-End Test
- [ ] Signal engine generates signal
- [ ] Signal saved to Supabase
- [ ] Frontend receives realtime update
- [ ] Telegram alert sent

### Step 2: Verify Components
- [ ] Backend: `curl YOUR_IP:8080/api/signals`
- [ ] Database: Check Supabase Table Editor
- [ ] Frontend: Dashboard shows data
- [ ] Telegram: Message received

### Step 3: Monitor
- [ ] AWS CloudWatch (EC2 metrics)
- [ ] Vercel Analytics (frontend)
- [ ] Supabase Dashboard (database)
- [ ] UptimeRobot (external monitoring)

**Status: ✅ SYSTEM LIVE**

---

## Phase 5: OPTIMIZATION (Optional)

### Performance
- [ ] Add CDN (Cloudflare)
- [ ] Enable caching
- [ ] Optimize images
- [ ] Add compression

### Security
- [ ] Enable SSL (HTTPS)
- [ ] Add rate limiting
- [ ] Configure CORS properly
- [ ] Add API authentication

### Monitoring
- [ ] Setup alerts
- [ ] Add logging
- [ ] Create dashboards
- [ ] Configure backups

---

## DEPLOYMENT FILES

All deployment scripts are in `/deploy/`:

```
deploy/
├── supabase/
│   ├── schema.sql          # Database schema
│   ├── seed.sql            # Sample data
│   └── policies.sql        # RLS policies
├── aws/
│   ├── ec2-setup.sh        # EC2 setup script
│   ├── user-data.sh        # Cloud-init script
│   └── cloudformation.yaml # Infrastructure as code
├── vercel/
│   ├── vercel.json         # Vercel config
│   └── build.sh            # Build script
├── docker/
│   ├── Dockerfile            # Container
│   └── docker-compose.yml    # Local development
└── scripts/
    ├── deploy.sh           # One-click deploy
    ├── update.sh           # Update app
    └── backup.sh           # Backup database
```

---

## QUICK COMMANDS

### Deploy Everything
```bash
# Clone repo
git clone https://github.com/manojkumar12-maker/binance-signal-engine.git
cd binance-signal-engine

# Setup Supabase (manual)
# Follow Phase 1 above

# Deploy backend
./deploy/aws/ec2-setup.sh

# Deploy frontend
./deploy/vercel/build.sh
```

### Update App
```bash
# Backend
cd ~/binance-signal-engine
git pull
pip install -r requirements.txt
sudo systemctl restart binance-signal

# Frontend
# Auto-deploys from GitHub
```

### Backup
```bash
# Database
supabase db dump

# EC2
aws ec2 create-image --instance-id i-xxx
```

---

## TROUBLESHOOTING

### Backend Not Running
```bash
# Check logs
sudo journalctl -u binance-signal -f

# Restart
sudo systemctl restart binance-signal

# Check port
sudo lsof -i :8080
```

### Frontend Not Loading
```bash
# Check Vercel logs
# Project → Deployments → Logs

# Check CORS
# Browser console for errors
```

### Database Not Connecting
```bash
# Check Supabase status
# https://status.supabase.com

# Test connection
python -c "from supabase import create_client; c = create_client('url', 'key'); print('OK')"
```

---

## COST SUMMARY

| Component | Service | Cost/Month |
|-----------|---------|-----------|
| Database | Supabase Free | $0 |
| Backend | AWS EC2 t2.micro | $0 |
| Frontend | Vercel Free | $0 |
| Domain | Freenom/DuckDNS | $0 |
| Monitoring | UptimeRobot | $0 |
| **Total** | | **$0** |

---

## NEXT STEPS

1. ✅ Create Supabase project
2. ✅ Deploy to EC2
3. ✅ Deploy to Vercel
4. ✅ Test everything
5. 🔄 Monitor performance
6. 🔄 Optimize
7. 🔄 Scale if needed

**Time to production: ~32 minutes**

**Status: 🚀 READY TO DEPLOY**
