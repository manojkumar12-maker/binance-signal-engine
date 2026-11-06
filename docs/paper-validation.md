# Paper Validation Guide

## Verification
- Confirm `TRADING_MODE=paper` in environment.
- `GET /api/status` shows trading_mode=paper and live_authorized=false.
- Run for 48-72 hours.
- Check scanner cycles in logs.
- Verify signals saved in `/api/scanner/results`.
- Verify Rug Check runs.
- Verify sizer approvals/rejections.
- Verify paper executions in `/api/paper/trades`.
- Verify equity snapshots in `/api/equity/history`.
- Restart app and confirm no duplicate trades and positions monitored.

## Empty States
- If no valid signals, dashboard shows empty states; do not fabricate activity.