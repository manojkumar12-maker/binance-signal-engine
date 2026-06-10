# QUICK DEPLOY TO VERCEL

## Step 1: Deploy Dashboard
```bash
# Install Vercel CLI (if not already installed)
npm i -g vercel

# Login to Vercel
vercel login

# Deploy from project root
cd C:\Users\a2dpo\Projects\binance-signal-engine
vercel --prod

# Follow prompts:
# - Set up and deploy? Yes
# - Link to existing project? No
# - Project name: binance-signal-dashboard
# - Directory: . (current directory)
```

## Step 2: Configure Environment Variables
```bash
# Add your EC2 IP as environment variable
vercel env add API_URL
# Enter: http://your-ec2-ip:8080/api

# Or set in Vercel Dashboard:
# Project Settings → Environment Variables
# Add: API_URL = http://your-ec2-ip:8080/api
```

## Step 3: Update Dashboard
After deployment, update the API URL in `dashboard.html`:

```javascript
const API = 'http://your-ec2-ip:8080/api';
// or
const API = 'https://your-backend-domain.com/api';
```

## Step 4: Redeploy
```bash
vercel --prod
```

## Alternative: Manual Deploy via Website
```
1. Go to https://vercel.com
2. Sign up with GitHub
3. Click "Add New Project"
4. Import your GitHub repo
5. Configure:
   - Framework: Other
   - Root Directory: . (root)
   - Build Command: (leave empty)
   - Output Directory: . (root)
6. Click Deploy
7. Add Environment Variables in Settings
```

## URL
After deployment:
```
https://binance-signal-dashboard.vercel.app
```

## IMPORTANT
The dashboard needs to connect to your backend (EC2/Oracle). Make sure:
1. Backend is running
2. API URL is correct in dashboard.html
3. CORS is enabled on backend
4. Security group allows connections from Vercel IPs

## Free Tier Limits
- Bandwidth: 100GB/month
- Function calls: 1M/month
- Build time: 6000min/month
- Perfect for a dashboard!
