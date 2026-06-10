# SYSTEM ARCHITECTURE

```
┌─────────────────────────────────────────────────────────────┐
│                        USER                                 │
│                        (Browser)                            │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ HTTPS
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  FRONTEND (Vercel)                                          │
│  ├─ React Dashboard (Next.js)                               │
│  ├─ Real-time Signal Display                                │
│  ├─ Trade Management UI                                     │
│  ├─ Performance Analytics                                   │
│  └─ WebSocket: Live Updates                                 │
│  URL: https://binance-signals.vercel.app                    │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ API Calls (REST + WebSocket)
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  SUPABASE (PostgreSQL)                                      │
│  ├─ signals table (active signals)                          │
│  ├─ trades table (trade history)                            │
│  ├─ analytics table (performance metrics)                   │
│  ├─ Realtime: Live updates to frontend                    │
│  └─ Row Level Security (RLS)                              │
│  URL: https://xyz.supabase.co                               │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ Read/Write
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  SIGNAL ENGINE (AWS EC2)                                    │
│  ├─ Scanner (60s loop)                                       │
│  ├─ Signal Generation (12 indicators)                       │
│  ├─ Risk Management                                         │
│  ├─ Telegram Alerts                                         │
│  └─ API Server (Flask)                                      │
│  URL: http://ec2-xxx.amazonaws.com:8080                    │
│  IP: Elastic IP (static)                                    │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ API Calls
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  BINANCE API                                                │
│  ├─ Klines (price data)                                     │
│  ├─ Open Interest                                           │
│  ├─ Funding Rates                                           │
│  ├─ Ticker/24hr (volume)                                    │
│  └─ WebSocket (real-time)                                   │
│  URL: https://fapi.binance.com                              │
└─────────────────────────────────────────────────────────────┘
```

## Data Flow

### 1. Signal Generation Flow
```
Signal Engine (EC2) ──► Binance API ──► Fetch klines
     │
     ▼
Process with 12 indicators
     │
     ▼
Save to Supabase (signals table)
     │
     ▼
Push to Frontend (Realtime)
     │
     ▼
Send Telegram Alert
```

### 2. Frontend Data Flow
```
Frontend (Vercel) ──► Supabase API ──► Fetch signals
     │
     ▼
Display in Dashboard
     │
     ▼
User clicks "Execute"
     │
     ▼
POST to Signal Engine API
     │
     ▼
Engine processes trade
     │
     ▼
Update Supabase (trades table)
     │
     ▼
Realtime update to Frontend
```

## Component Details

### Frontend (Vercel)
- **Framework**: React/Next.js (or static HTML)
- **Hosting**: Vercel (free tier)
- **Features**: Real-time dashboard, trade management, analytics
- **API**: REST to Supabase + Signal Engine
- **Cost**: Free

### Supabase (PostgreSQL)
- **Database**: PostgreSQL
- **Features**: Realtime, Auth, Storage, Edge Functions
- **Tables**: signals, trades, analytics, settings
- **Cost**: Free tier (500MB, 2GB bandwidth)
- **URL**: https://your-project.supabase.co

### Signal Engine (AWS EC2)
- **Instance**: t2.micro (free tier) or t3.small
- **OS**: Ubuntu 22.04
- **Runtime**: Python 3.11
- **Server**: Gunicorn + Flask
- **Features**: Scanner, signal generation, risk management
- **Cost**: Free (t2.micro) or ~$15/month (t3.small)
- **IP**: Elastic IP (static)

### Binance API
- **Data**: Price, volume, OI, funding
- **Rate Limit**: 1200 requests/minute
- **WebSocket**: Real-time updates
- **Cost**: Free

## API Endpoints

### Signal Engine (EC2)
```
GET  /health              → Health check
GET  /api/signals         → Active signals
GET  /api/signal/<pair>   → Signal for pair
GET  /api/trades          → Trade history
POST /api/trade/open      → Open trade
GET  /api/analytics        → Performance metrics
GET  /api/system-status    → System status
```

### Supabase (Database)
```
GET  /rest/v1/signals     → Active signals
GET  /rest/v1/trades      → Trade history
GET  /rest/v1/analytics   → Performance data
POST /rest/v1/signals     → Create signal
POST /rest/v1/trades      → Create trade
```

## Environment Variables

### Frontend (Vercel)
```
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key
NEXT_PUBLIC_SIGNAL_ENGINE_URL=http://your-ec2-ip:8080
```

### Signal Engine (EC2)
```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=your-service-key
TELEGRAM_BOT_TOKEN=your-bot-token
TELEGRAM_CHAT_ID=your-chat-id
BINANCE_API_KEY=your-api-key
BINANCE_SECRET_KEY=your-secret-key
PORT=8080
```

## Security

### 1. Supabase RLS (Row Level Security)
```sql
-- Enable RLS on tables
ALTER TABLE signals ENABLE ROW LEVEL SECURITY;
ALTER TABLE trades ENABLE ROW LEVEL SECURITY;

-- Policy: Only allow reads
CREATE POLICY "Allow public reads" ON signals
    FOR SELECT USING (true);

-- Policy: Only service role can write
CREATE POLICY "Allow service writes" ON signals
    FOR INSERT WITH CHECK (auth.role() = 'service_role');
```

### 2. API Security
- CORS enabled (frontend domain only)
- Rate limiting (100 requests/minute)
- API key for sensitive endpoints
- JWT validation for Supabase

### 3. Network Security
- EC2 Security Group: Only allow 8080 from frontend
- Supabase: IP whitelist for EC2
- Vercel: HTTPS only

## Scaling

### Current (Free Tier)
- Frontend: Vercel (unlimited requests)
- Database: Supabase (500MB)
- Engine: EC2 t2.micro (1 CPU, 1GB RAM)
- Signals: 3-8/day

### Future (Paid)
- Frontend: Vercel Pro ($20/month)
- Database: Supabase Pro ($25/month)
- Engine: EC2 t3.medium (2 CPU, 4GB RAM) - $30/month
- Signals: 100+ pairs
- Total: ~$75/month

## Monitoring

### 1. Application Monitoring
- Vercel Analytics (built-in)
- Supabase Dashboard (built-in)
- AWS CloudWatch (EC2 metrics)

### 2. Uptime Monitoring
- UptimeRobot (free) - checks every 5 minutes
- StatusCake (free) - 10-minute intervals
- PagerDuty (paid) - alerts

### 3. Logs
- Vercel: Function logs (built-in)
- Supabase: Database logs (built-in)
- EC2: journalctl + CloudWatch

## Deployment Order

### Phase 1: Setup Infrastructure
1. Create Supabase project
2. Create database tables
3. Create EC2 instance
4. Configure security groups
5. Get Elastic IP

### Phase 2: Deploy Signal Engine
1. SSH into EC2
2. Install dependencies
3. Clone repo
4. Setup environment variables
5. Start systemd service
6. Test endpoints

### Phase 3: Deploy Frontend
1. Create Vercel account
2. Connect GitHub repo
3. Configure environment variables
4. Deploy
5. Test connections

### Phase 4: Integration Testing
1. Test signal flow end-to-end
2. Verify realtime updates
3. Test Telegram alerts
4. Monitor performance

## Cost Breakdown (Free Tier)

| Component | Service | Cost |
|-----------|---------|------|
| Frontend | Vercel | Free |
| Database | Supabase | Free |
| Backend | AWS EC2 t2.micro | Free (12 months) |
| Domain | None | Free (use IP) |
| Monitoring | UptimeRobot | Free |
| **Total** | | **$0** |

## Next Steps

1. **Create Supabase project** (5 minutes)
2. **Create EC2 instance** (10 minutes)
3. **Deploy signal engine** (10 minutes)
4. **Deploy frontend** (5 minutes)
5. **Test everything** (10 minutes)

**Total setup time: ~40 minutes**

---

## Files You Need

### 1. Database Schema
```sql
-- Create signals table
CREATE TABLE signals (
    id SERIAL PRIMARY KEY,
    pair TEXT NOT NULL,
    signal TEXT NOT NULL, -- BUY, SELL, NO TRADE
    entry NUMERIC,
    sl NUMERIC,
    tp1 NUMERIC,
    tp2 NUMERIC,
    tp3 NUMERIC,
    confidence INTEGER,
    regime TEXT,
    tier TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    executed BOOLEAN DEFAULT FALSE
);

-- Create trades table
CREATE TABLE trades (
    id SERIAL PRIMARY KEY,
    pair TEXT NOT NULL,
    direction TEXT NOT NULL,
    entry NUMERIC,
    exit NUMERIC,
    pnl NUMERIC,
    status TEXT, -- OPEN, TP1, TP2, TP3, SL
    created_at TIMESTAMP DEFAULT NOW(),
    closed_at TIMESTAMP
);

-- Create analytics table
CREATE TABLE analytics (
    id SERIAL PRIMARY KEY,
    metric TEXT NOT NULL,
    value NUMERIC,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### 2. Supabase Client (Python)
```python
from supabase import create_client

supabase = create_client(
    "https://your-project.supabase.co",
    "your-service-key"
)

# Insert signal
supabase.table("signals").insert({
    "pair": "BTCUSDT",
    "signal": "BUY",
    "entry": 45000,
    "confidence": 85,
    "tier": "ELITE"
}).execute()

# Get active signals
response = supabase.table("signals").select("*").eq("executed", False).execute()
```

### 3. Frontend (React)
```jsx
import { createClient } from '@supabase/supabase-js'

const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL,
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY
)

// Subscribe to realtime signals
supabase
  .channel('signals')
  .on('postgres_changes', { event: 'INSERT', schema: 'public', table: 'signals' }, payload => {
    console.log('New signal:', payload.new)
  })
  .subscribe()
```

## Complete Implementation

All files are in this repo:
- `frontend/` - Next.js app (deploy to Vercel)
- `app/core/` - Signal engine (deploy to EC2)
- `supabase/schema.sql` - Database schema
- `aws/ec2-setup.sh` - EC2 setup script
- `vercel.json` - Vercel configuration

---

## Support & Monitoring

- **Vercel Status**: https://status.vercel.com
- **Supabase Status**: https://status.supabase.com
- **AWS Status**: https://status.aws.amazon.com
- **Your App**: UptimeRobot monitoring

## Troubleshooting

### 1. Frontend can't connect to API
- Check CORS settings on EC2
- Verify EC2 security group allows port 8080
- Check if EC2 is running

### 2. Database connection errors
- Verify Supabase URL and key
- Check Supabase project status
- Verify IP whitelist

### 3. Signal engine not generating signals
- Check EC2 logs: `journalctl -u binance-signal -f`
- Verify Binance API rate limits
- Check if scanner is running

### 4. Telegram not working
- Verify bot token
- Check if bot is added to chat
- Verify chat ID

---

## Architecture Benefits

✅ **Decoupled**: Frontend, database, engine are independent
✅ **Scalable**: Each component can scale independently
✅ **Reliable**: If one fails, others continue
✅ **Fast**: Vercel CDN + Supabase caching
✅ **Secure**: RLS, CORS, API keys
✅ **Cost-effective**: All free tiers
✅ **Real-time**: Supabase realtime updates
✅ **Professional**: Institutional-grade architecture

---

## Migration from Current Setup

### Current (Monolithic)
```
Railway (Flask + Redis + HTML)
```

### New (Distributed)
```
Vercel (Frontend) + Supabase (DB) + EC2 (Engine) + Binance (API)
```

### Steps
1. Move frontend to Vercel (deploy HTML or React)
2. Create Supabase database
3. Migrate data from Redis to Supabase
4. Deploy engine to EC2
5. Update API endpoints
6. Test everything

**Downtime: ~30 minutes**

---

## Summary

You now have a **production-grade, scalable architecture** that costs **$0** and can handle **100+ pairs** with **24/7 uptime**.

**Next step**: Pick a component and start deploying!
