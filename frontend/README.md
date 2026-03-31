# Binance Signal Engine - Frontend

## Deploy to GitHub Pages

1. Create a new repository on GitHub
2. Push this folder to the repository:
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
   git push -u origin main
   ```
3. Go to Repository Settings → Pages
4. Set Source to "Deploy from a branch"
5. Select `main` branch and `/ (root)` folder
6. Click Save

## Configuration

Edit `app.js` to change the backend URL:
```javascript
const API_BASE_URL = 'https://your-backend.up.railway.app/api';
```

Replace `your-backend.up.railway.app` with your actual Railway app URL.

## Features

- Trading pair selector (BTC, ETH, BNB, SOL, etc.)
- Timeframe selection (15m, 1H, 4H)
- Real-time signal display
- Entry, Stop Loss, TP1, TP2, TP3 levels
- Confidence score visualization
- Strategy indicators (Trend, Liquidity, Volume)
- Auto-refresh every 5 minutes
