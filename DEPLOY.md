# 🚀 Deploy to Railway

## Quick Deploy

1. Go to [railway.app](https://railway.app)
2. Login with GitHub
3. Click **New Project** → **Deploy from GitHub repo**
4. Select `manojkumar12-maker/binance-signal-engine`
5. Railway auto-detects Node.js

## Manual Setup

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login
railway login

# Deploy
cd binance-signal-engine
railway init
railway up
```

## Environment Variables

Optional - add in Railway dashboard:
- `PORT` (default: 3000)

## API Endpoints

After deployment:
- `https://your-app.railway.app/api/signals` - Get all signals
- `https://your-app.railway.app/api/health` - Health check

## WebSocket

Connect to:
- `wss://your-app.railway.app` (if configured)

## Update Frontend

Edit `frontend/index.html` line ~170:
```javascript
const wsUrl = 'wss://your-railway-app.railway.app';
```

Then push changes to deploy automatically.
