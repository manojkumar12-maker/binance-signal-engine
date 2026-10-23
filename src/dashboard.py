"""FastAPI dashboard exposing status and mobile-friendly UI."""
import os
import time
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse

from .config import settings
from .storage import Storage
from .kill_switch import KillSwitch

app = FastAPI(title="Binance Signal Engine Status")
storage = Storage()
kill = KillSwitch(storage)

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")

_rate = {}


def rate_limit(ip: str, limit: int = 120):
    now = time.time()
    r = _rate.get(ip)
    if not r or now > r[1]:
        _rate[ip] = [1, now + 60]
        return True
    if r[0] >= limit:
        return False
    r[0] += 1
    return True


@app.middleware("http")
async def rl_middleware(request: Request, call_next):
    ip = request.client.host if request.client else "unknown"
    if not rate_limit(ip):
        return JSONResponse({"error": "rate limited"}, status_code=429)
    return await call_next(request)


def _auth(request: Request):
    if not ADMIN_TOKEN:
        return
    token = request.headers.get("X-Admin-Token") or request.query_params.get("token")
    if token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="forbidden")


@app.get("/health")
def health():
    return {"status": "ok", "mode": settings.trading_mode, "live_authorized": settings.live_authorized}


@app.get("/status")
def status():
    halted, reason = kill.is_halted()
    hb = storage.get_heartbeat()
    return {
        "health": "ok",
        "trading_mode": settings.trading_mode,
        "live_authorized": settings.live_authorized,
        "broker_enabled": settings.broker_enabled,
        "auto_trade": settings.auto_trade,
        "live_trading_enabled": settings.live_trading_enabled,
        "use_testnet": settings.use_testnet,
        "simulated_starting_balance": str(settings.simulated_starting_balance),
        "open_positions": len(storage.open_positions()),
        "daily_loss_used": str(kill.daily_loss_used()),
        "daily_loss_remaining": str(kill.daily_loss_remaining()),
        "halted": halted,
        "halt_reason": reason,
        "worker_heartbeat": hb,
    }


@app.get("/signals")
def signals():
    cur = storage.conn.cursor()
    cur.execute("SELECT symbol,direction,timestamp,entry_price,stop_loss,take_profit,accepted,rejection_reason FROM signals ORDER BY id DESC LIMIT 50")
    rows = cur.fetchall()
    cols = ["symbol", "direction", "timestamp", "entry_price", "stop_loss", "take_profit", "accepted", "rejection_reason"]
    return {"signals": [dict(zip(cols, r)) for r in rows]}


@app.get("/trades")
def trades():
    cur = storage.conn.cursor()
    cur.execute("SELECT id,symbol,direction,entry_price,stop_loss,take_profit,quantity,status,opened_at,closed_at,realized_pnl,fees FROM trades ORDER BY id DESC LIMIT 50")
    rows = cur.fetchall()
    cols = ["id", "symbol", "direction", "entry_price", "stop_loss", "take_profit", "quantity", "status", "opened_at", "closed_at", "realized_pnl", "fees"]
    return {"trades": [dict(zip(cols, r)) for r in rows]}


@app.post("/halt")
def halt(request: Request):
    _auth(request)
    kill.halt("manual halt via dashboard")
    return {"halted": True}


@app.post("/resume")
def resume(request: Request):
    _auth(request)
    kill.reset(operator_confirmed=True)
    return {"halted": False}


@app.get("/", response_class=HTMLResponse)
def index():
    ui_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ui", "index.html")
    if os.path.exists(ui_path):
        return FileResponse(ui_path)
    return HTMLResponse("<h1>Binance Signal Engine</h1><p>UI not found.</p>")