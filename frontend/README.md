# Binance Signal Engine - React Dashboard

Real-time trading dashboard powered by WebSocket.

## Setup

```bash
cd frontend
npm install
npm run build
```

The build output will be in `build/` folder - deploy this to GitHub Pages.

## Configuration

Set environment variable to point to your backend:
- `REACT_APP_API_URL` - Backend API URL (e.g., `https://binance-signal-engine-production.up.railway.app/api`)
- `REACT_APP_SOCKET_URL` - WebSocket server URL (e.g., `https://binance-signal-engine-production.up.railway.app`)

## Features

- Real-time signal pipeline visualization
- Live trade monitoring with PnL
- Auto-refresh via WebSocket (with HTTP fallback)
- Responsive design
