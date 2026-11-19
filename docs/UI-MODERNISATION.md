# UI Modernisation — Migration Notes

Scope: replace the legacy dashboard front end (`engine/ui/index.html`) with the
"Aurora Control UI" while keeping the FastAPI backend (`engine/src/dashboard.py`)
and its API contract unchanged. No database or runtime migration was needed —
the data layer (SQLite under `engine/data/`) is untouched.

## What behaviour had to be preserved exactly

- All existing API endpoints and response shapes (`/status`, `/signals`,
  `/trades`, `/api/logs`, `/api/equity/analytics`, `/api/sizer/config`,
  `/api/scanner/*`, `/api/admin/*`, `/ws`).
- Admin session auth (same `ADMIN_USERNAME` / `ADMIN_PASSWORD` env vars, same
  401-before-login behaviour).
- Orchestrator behaviour: daily loss budget accounting on closed trades,
  cooldown persistence, sizer R:R gate and position cap (covered by the
  existing 167-test suite).

## Phases (each left the app working)

1. **Static shell + tokens** — new layout, colour/typography tokens, local
   fonts (`ui/fonts/`, no external font CDN request). Backend untouched.
   Rollback: `git revert` the single commit; the old `index.html` is in history.
2. **Live data wiring** — views (Overview, Scanner, Rug Check, Sizer,
   Executer, Portfolio, Logger, Admin Logs, Settings) bound to the existing
   endpoints; polling fallback when the `/ws` handshake is blocked by a proxy.
   Rollback: revert commit.
3. **Hero position panel + vitality strip** — in-flight position, stop/target
   rail, agent pipeline. Fixed the Decimal formatting bug: stop/target are
   rendered via `Number(v).toPrecision(8)` with trailing zeros stripped
   (`ui/index.html:1086`) instead of raw DB Decimal strings.
4. **Loss-budget fix** — manual trade close now records realized P&L against
   the daily loss budget (backend, tested).

## Verification per phase

- `python -m pytest -q` in `engine/`: 167 passed (latest run, 7.0s).
- Headless-browser smoke at 390px and 1280px: login → hero panel with live
  DASHUSDT position, clean stop/target values, no horizontal overflow, no page
  errors. Pre-login 401 fetches are expected (auth gate); a 403 on the `/ws`
  handshake comes from the preview proxy — the app falls back to polling.

## Deprecations / known follow-ups

- Old UI markup no longer exists; any external bookmark to anchors of the old
  page will land on the new single-page console.
- The WebSocket 403 behind the preview proxy is environmental; in production
  behind a WS-capable proxy the socket connects.

## Rollback for the current state

`git revert 65fda3e 8734360` restores the pre-modernisation dashboard; the
backend and data schema are compatible in both directions, so a revert needs no
data migration.
