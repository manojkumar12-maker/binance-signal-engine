# SUPABASE SETUP GUIDE

## 1. Create Project
```
https://supabase.com
1. Sign up with GitHub
2. Create new project
3. Name: binance-signal-engine
4. Database password: (save this!)
5. Region: Closest to you (Mumbai for India)
6. Wait 2-3 minutes for setup
```

## 2. Get Credentials
```
Project Settings → API

URL: https://xyzxyzxyzxyz.supabase.co
anon public: eyJ... (for frontend)
service_role: eyJ... (for backend - KEEP SECRET!)

Project Settings → Database → Connection string
```

## 3. Create Tables

Go to SQL Editor → New Query → Paste:

```sql
-- Enable Row Level Security
ALTER DATABASE postgres SET "app.jwt_secret" TO 'your-jwt-secret';

-- Create signals table
CREATE TABLE signals (
    id SERIAL PRIMARY KEY,
    pair TEXT NOT NULL,
    signal TEXT NOT NULL CHECK (signal IN ('BUY', 'SELL', 'NO TRADE')),
    entry NUMERIC,
    sl NUMERIC,
    tp1 NUMERIC,
    tp2 NUMERIC,
    tp3 NUMERIC,
    confidence INTEGER CHECK (confidence >= 0 AND confidence <= 100),
    regime TEXT,
    tier TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    executed BOOLEAN DEFAULT FALSE
);

-- Create trades table
CREATE TABLE trades (
    id SERIAL PRIMARY KEY,
    pair TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('BUY', 'SELL')),
    entry NUMERIC NOT NULL,
    exit NUMERIC,
    pnl NUMERIC,
    status TEXT DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'TP1', 'TP2', 'TP3', 'SL')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    closed_at TIMESTAMP WITH TIME ZONE
);

-- Create analytics table
CREATE TABLE analytics (
    id SERIAL PRIMARY KEY,
    metric TEXT NOT NULL,
    value NUMERIC,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for performance
CREATE INDEX idx_signals_created ON signals (created_at DESC);
CREATE INDEX idx_signals_pair ON signals (pair);
CREATE INDEX idx_signals_executed ON signals (executed);
CREATE INDEX idx_trades_status ON trades (status);
CREATE INDEX idx_trades_pair ON trades (pair);
CREATE INDEX idx_analytics_metric ON analytics (metric, created_at DESC);

-- Enable Row Level Security
ALTER TABLE signals ENABLE ROW LEVEL SECURITY;
ALTER TABLE trades ENABLE ROW LEVEL SECURITY;
ALTER TABLE analytics ENABLE ROW LEVEL SECURITY;

-- Policies: Allow public reads (for frontend)
CREATE POLICY "Allow public reads on signals" ON signals
    FOR SELECT TO anon USING (true);

CREATE POLICY "Allow public reads on trades" ON trades
    FOR SELECT TO anon USING (true);

CREATE POLICY "Allow public reads on analytics" ON analytics
    FOR SELECT TO anon USING (true);

-- Policies: Only service role can write (for backend)
CREATE POLICY "Allow service writes on signals" ON signals
    FOR INSERT TO service_role WITH CHECK (true);

CREATE POLICY "Allow service writes on trades" ON trades
    FOR INSERT TO service_role WITH CHECK (true);

CREATE POLICY "Allow service writes on analytics" ON analytics
    FOR INSERT TO service_role WITH CHECK (true);

-- Allow service role to update
CREATE POLICY "Allow service updates on signals" ON signals
    FOR UPDATE TO service_role USING (true);

CREATE POLICY "Allow service updates on trades" ON trades
    FOR UPDATE TO service_role USING (true);
```

Click **Run** to execute.

## 4. Enable Realtime
```
Database → Replication
→ Turn on "Realtime" for tables:
   - signals
   - trades
   - analytics
```

## 5. Test Connection

### From Backend (Python)
```python
from supabase import create_client

supabase = create_client(
    "https://your-project.supabase.co",
    "your-service-role-key"
)

# Test insert
supabase.table("signals").insert({
    "pair": "BTCUSDT",
    "signal": "BUY",
    "confidence": 85,
    "tier": "ELITE"
}).execute()

# Test select
response = supabase.table("signals").select("*").execute()
print(response.data)
```

### From Frontend (JavaScript)
```javascript
import { createClient } from '@supabase/supabase-js'

const supabase = createClient(
  'https://your-project.supabase.co',
  'your-anon-key'
)

// Subscribe to realtime
supabase
  .channel('signals')
  .on('postgres_changes', { event: 'INSERT', schema: 'public', table: 'signals' }, payload => {
    console.log('New signal:', payload.new)
  })
  .subscribe()

// Fetch signals
const { data, error } = await supabase
  .from('signals')
  .select('*')
  .eq('executed', false)
  .order('created_at', { ascending: false })
  .limit(10)
```

## 6. Environment Variables

### Backend (.env)
```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-service-role-key
```

### Frontend (Vercel)
```
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key
```

## 7. Monitoring

```
Supabase Dashboard → Usage
- Database size: 500MB limit (free)
- API requests: 500K/month (free)
- Realtime: 200 concurrent (free)
- Auth: 50K users/month (free)
```

## 8. Backup

```
Supabase Dashboard → Database → Backups
- Automated daily backups
- Point-in-time recovery (7 days)
```

## 9. Scaling (Paid)

When you need more:
```
Pro Plan: $25/month
- 8GB database
- 100GB bandwidth
- 500K auth users
- Priority support

Team Plan: $599/month
- 40GB database
- 1TB bandwidth
- Unlimited auth
- SSO support
```

## 10. Troubleshooting

### Connection Error
```python
# Check if URL is correct
# Check if key is correct (service_role for backend, anon for frontend)
# Check if project is active (not paused)
```

### RLS Error
```
# Check if policies are created
# Check if user has correct role
# Use service_role key for backend writes
```

### Realtime Not Working
```
# Check if realtime is enabled in table
# Check if you're using correct channel name
# Check if you have permission to listen
```

## Summary

✅ Database created
✅ Tables created
✅ Indexes created
✅ RLS enabled
✅ Realtime enabled
✅ Credentials saved

**Cost: $0 (free tier)**

**Next:** Connect your signal engine to Supabase
