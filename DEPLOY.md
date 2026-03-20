# Deploy to Fly.io

## Quick Deploy

1. Install Fly CLI:
   ```bash
   fly install
   ```

2. Login to Fly.io:
   ```bash
   fly auth login
   ```

3. Launch the app:
   ```bash
   fly launch
   ```

4. Set secrets (if needed):
   ```bash
   fly secrets set API_KEY=your_api_key
   ```

5. Deploy:
   ```bash
   fly deploy
   ```

6. Open your app:
   ```bash
   fly open
   ```

## Manual Setup

1. Create app:
   ```bash
   fly apps create binance-signals
   ```

2. Deploy:
   ```bash
   fly deploy
   ```

3. Check status:
   ```bash
   fly status
   ```

## Scaling

- Scale VMs:
  ```bash
  fly scale count 1
  ```

- Scale memory:
  ```bash
  fly scale memory 256
  ```

## Logs

```bash
fly logs
```

## Regions

Default region is `iad` (Virginia). To change, edit `fly.toml`:
```toml
primary_region = "lax"  # Los Angeles
```

Available regions: `iad`, `lax`, `ord`, `atl`, `sea`, `dfw`, `syd`, `fra`, `ams`
