# VERCEL DEPLOYMENT GUIDE

## What You Get

- **Free hosting** (forever)
- **Global CDN** (fast worldwide)
- **Auto-deploy** from GitHub
- **HTTPS** included
- **Serverless Functions** (API routes)
- **Preview deployments** (per PR)
- **Custom domains** (free)
- **Analytics** (built-in)

## Prerequisites

1. GitHub account (https://github.com)
2. Vercel account (https://vercel.com)
3. Your repo on GitHub

---

## OPTION 1: Deploy Current Frontend (HTML)

### Step 1: Update vercel.json
```json
{
  "version": 2,
  "routes": [
    {
      "src": "/(.*)",
      "dest": "/dashboard.html"
    }
  ]
}
```

### Step 2: Deploy
```
1. Go to https://vercel.com
2. Sign up with GitHub
3. Click "Add New Project"
4. Import your GitHub repo
5. Framework: Other
6. Build Command: (leave empty)
7. Output Directory: .
8. Click "Deploy"

Wait 30 seconds...
Done! Your frontend is live!
```

**URL:** `https://your-project.vercel.app`

---

## OPTION 2: Deploy Modern React Frontend (RECOMMENDED)

### Step 1: Create React App
```bash
# Create Next.js app
npx create-next-app frontend

# Or use existing
```

### Step 2: Install Dependencies
```bash
cd frontend
npm install @supabase/supabase-js
npm install axios
npm install recharts
```

### Step 3: Create Pages

#### app/page.tsx (Dashboard)
```tsx
'use client'

import { useEffect, useState } from 'react'
import { createClient } from '@supabase/supabase-js'

const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL,
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY
)

export default function Dashboard() {
  const [signals, setSignals] = useState([])
  const [trades, setTrades] = useState([])

  useEffect(() => {
    // Fetch signals
    fetchSignals()
    fetchTrades()

    // Subscribe to realtime
    const channel = supabase
      .channel('signals')
      .on('postgres_changes', { event: 'INSERT', schema: 'public', table: 'signals' }, payload => {
        setSignals(prev => [payload.new, ...prev])
      })
      .subscribe()

    return () => {
      supabase.removeChannel(channel)
    }
  }, [])

  async function fetchSignals() {
    const { data } = await supabase
      .from('signals')
      .select('*')
      .eq('executed', false)
      .order('created_at', { ascending: false })
      .limit(10)
    
    if (data) setSignals(data)
  }

  async function fetchTrades() {
    const { data } = await supabase
      .from('trades')
      .select('*')
      .order('created_at', { ascending: false })
      .limit(10)
    
    if (data) setTrades(data)
  }

  return (
    <div className="p-8">
      <h1 className="text-3xl font-bold mb-8">Binance Signal Engine</h1>
      
      <div className="grid grid-cols-2 gap-8">
        {/* Active Signals */}
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-xl font-semibold mb-4">Active Signals</h2>
          <div className="space-y-4">
            {signals.map(signal => (
              <div key={signal.id} className="border p-4 rounded">
                <div className="flex justify-between">
                  <span className="font-bold">{signal.pair}</span>
                  <span className={`px-2 py-1 rounded ${signal.signal === 'BUY' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
                    {signal.signal}
                  </span>
                </div>
                <div className="mt-2 text-sm text-gray-600">
                  Confidence: {signal.confidence}% | Tier: {signal.tier}
                </div>
                <div className="mt-1 text-sm">
                  Entry: {signal.entry} | SL: {signal.sl} | TP: {signal.tp1}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Recent Trades */}
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-xl font-semibold mb-4">Recent Trades</h2>
          <div className="space-y-4">
            {trades.map(trade => (
              <div key={trade.id} className="border p-4 rounded">
                <div className="flex justify-between">
                  <span className="font-bold">{trade.pair}</span>
                  <span className={`px-2 py-1 rounded ${trade.pnl > 0 ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
                    {trade.pnl > 0 ? '+' : ''}{trade.pnl}%
                  </span>
                </div>
                <div className="mt-2 text-sm text-gray-600">
                  Status: {trade.status} | Entry: {trade.entry}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
```

### Step 4: Create API Route

#### app/api/signals/route.ts
```typescript
import { NextResponse } from 'next/server'

export async function GET() {
  const response = await fetch(`${process.env.SIGNAL_ENGINE_URL}/api/signals`)
  const data = await response.json()
  return NextResponse.json(data)
}
```

### Step 5: Environment Variables

Create `.env.local`:
```
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key
SIGNAL_ENGINE_URL=http://your-ec2-ip:8080
```

### Step 6: Configure Vercel

Create `vercel.json`:
```json
{
  "version": 2,
  "buildCommand": "npm run build",
  "outputDirectory": ".next",
  "framework": "nextjs",
  "env": {
    "NEXT_PUBLIC_SUPABASE_URL": "@next_public_supabase_url",
    "NEXT_PUBLIC_SUPABASE_ANON_KEY": "@next_public_supabase_anon_key",
    "SIGNAL_ENGINE_URL": "@signal_engine_url"
  }
}
```

### Step 7: Deploy

```bash
# Push to GitHub
git add .
git commit -m "Add frontend"
git push origin master

# Deploy
# Vercel will auto-deploy from GitHub
```

Or manually:
```bash
# Install Vercel CLI
npm i -g vercel

# Deploy
vercel
```

---

## Environment Variables in Vercel

```
1. Go to https://vercel.com
2. Select your project
3. Settings → Environment Variables
4. Add:

   NEXT_PUBLIC_SUPABASE_URL = https://your-project.supabase.co
   NEXT_PUBLIC_SUPABASE_ANON_KEY = your-anon-key
   SIGNAL_ENGINE_URL = http://your-ec2-ip:8080

5. Click "Save"
6. Redeploy (if needed)
```

---

## Custom Domain (Free)

### Option 1: Vercel Subdomain
```
Already included: https://your-project.vercel.app
```

### Option 2: Custom Domain
```
1. Buy domain (Namecheap, GoDaddy, etc.)
2. Vercel → Project → Settings → Domains
3. Add domain
4. Update DNS:
   - Type: CNAME
   - Name: www
   - Value: cname.vercel-dns.com
   - OR: A record pointing to 76.76.21.21
5. Wait for SSL (auto-provisioned)
```

---

## Monitoring

```
Vercel Dashboard → Analytics
- Real-time visitors
- Core Web Vitals
- Performance metrics
- Error tracking

All free and built-in!
```

---

## Features

### Preview Deployments
```
Every PR gets its own URL:
https://your-project-git-branch.vercel.app
```

### Rollback
```
Deployments → Select version → Promote
```

### Functions
```
Serverless API routes:
- API calls
- Database queries
- Webhooks

All free!
```

---

## COST

| Feature | Free | Pro ($20) |
|---------|------|-----------|
| Bandwidth | 100GB | 1TB |
| Function calls | 1M | 10M |
| Build time | 6000min | 10000min |
| Team | 1 | 1 |
| Analytics | Basic | Advanced |

**For your signal engine: FREE tier is enough!**

---

## TROUBLESHOOTING

### Build Error
```
Check build logs in Vercel dashboard
Common issues:
- Missing dependencies
- TypeScript errors
- Environment variables not set
```

### CORS Error
```
Add to your EC2 backend:
response.headers['Access-Control-Allow-Origin'] = '*'

Or specific domain:
response.headers['Access-Control-Allow-Origin'] = 'https://your-project.vercel.app'
```

### Realtime Not Working
```
- Check if Supabase realtime is enabled
- Check if NEXT_PUBLIC_SUPABASE_URL is correct
- Check browser console for errors
```

---

## QUICK REFERENCE

```bash
# Deploy
vercel

# Deploy production
vercel --prod

# View logs
vercel logs

# View status
vercel status
```

---

## NEXT STEPS

1. ✅ Deploy frontend to Vercel
2. ✅ Add custom domain (optional)
3. ✅ Setup environment variables
4. ✅ Test realtime updates
5. ✅ Monitor performance

**Your frontend is live at:** `https://your-project.vercel.app` 🎉

---

## SUPPORT

- **Vercel Docs**: https://vercel.com/docs
- **Vercel Status**: https://status.vercel.com
- **Next.js Docs**: https://nextjs.org/docs
- **Supabase Docs**: https://supabase.com/docs
