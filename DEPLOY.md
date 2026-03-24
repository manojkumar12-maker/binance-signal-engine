# Deploy Binance Signal Engine

## Architecture

| Component | Platform | URL |
|-----------|----------|-----|
| Backend API | Railway | `https://<your-app>.up.railway.app` |
| PostgreSQL | Railway Plugin | Auto-configured |
| Redis Cache | Railway Plugin | Auto-configured |
| Frontend | GitHub Pages | `https://manojkumar12-maker.github.io/binance-signal-engine/` |

## 1. Deploy Backend to Railway

1. Go to [railway.app](https://railway.app) → **"New Project"** → **"Deploy from GitHub"**
2. Connect repo: `manojkumar12-maker/binance-signal-engine`
3. Add plugins:
   - Click **"+ New"** → **PostgreSQL** (database)
   - Click **"+ New"** → **Redis** (cache)
4. Railway auto-sets `DATABASE_URL`, `REDIS_URL`, and `PORT`
5. Add optional env vars in Railway dashboard:
   ```
   TELEGRAM_ENABLED=true
   TELEGRAM_BOT_TOKEN=your_token
   TELEGRAM_CHAT_ID=your_chat_id
   ```
6. Deploy triggers automatically on push to `main`

## 2. Deploy Frontend to GitHub Pages

1. Go to repo **Settings** → **Pages**
2. Under **Source**, select **GitHub Actions**
3. The workflow at `.github/workflows/deploy.yml` deploys `frontend/` on every push

### Update Backend URL

Edit `frontend/index.html` and set your Railway backend URL:

```javascript
// Line ~534 — replace with your actual Railway URL
window.BACKEND_URL = 'https://your-app-production.up.railway.app';
```

Or add a script tag before the dashboard script:

```html
<script>window.BACKEND_URL = 'https://your-app-production.up.railway.app';</script>
```

## 3. Local Development

```bash
# Start PostgreSQL + Redis locally
docker-compose up -d

# Copy env file
cp .env.example .env

# Install dependencies
npm install

# Run with dotenv
npm run dev
```

## API Endpoints

- `GET /api/health` — Health check
- `GET /api/signals` — All signals (JSON)
- `GET /api/stats` — Signal statistics
- `GET /` — Dashboard (served from backend)

## Notes

- Database auto-migrates on first start (creates `signals` table)
- If `DATABASE_URL` is not set, falls back to JSON file storage
- If `REDIS_URL` is not set, caching is disabled (still works)
- Railway Hobby plan keeps service always-on (no cold starts like Render free tier)
