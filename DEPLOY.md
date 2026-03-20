# Deploy to Render (Free Tier)

## Quick Deploy

1. Go to [render.com](https://render.com)
2. Click **"New +"** → **"Web Service"**
3. Connect your GitHub: `manojkumar12-maker/binance-signal-engine`
4. Configure:
   - **Name:** `binance-signals`
   - **Region:** Choose closest
   - **Branch:** `main`
   - **Root Directory:** (leave empty)
   - **Runtime:** `Node`
   - **Build Command:** `npm install`
   - **Start Command:** `node src/index.js`
   - **Plan:** `Free`

5. Click **"Create Web Service"**

## API Endpoints

After deploy:
- `https://binance-signals.onrender.com/api/signals`
- `https://binance-signals.onrender.com/api/health`

## Update Frontend

Edit `frontend/index.html`:
```javascript
const wsUrl = 'wss://binance-signals.onrender.com';
```

Or change the WebSocket URL to your deployed backend.

## Notes

- Free tier sleeps after 15 min of inactivity
- First deploy takes ~2-3 minutes
- Subsequent deploys are faster
