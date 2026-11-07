"""FastAPI dashboard exposing status and mobile-friendly UI."""
import os
import time
import asyncio
import json as _json
from fastapi import FastAPI, Request, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse

from .config import settings
from .storage import Storage
from .kill_switch import KillSwitch
from .auth import AuthManager
from .admin import AdminManager
from .settings_manager import SettingsManager

app = FastAPI(title="Binance Signal Engine Status")


def api_error_handler(func):
    import inspect
    from functools import wraps
    if inspect.iscoroutinefunction(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except HTTPException:
                raise
            except Exception as e:
                return JSONResponse({"error": str(e)}, status_code=500)
        return wrapper
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except HTTPException:
            raise
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)
    return wrapper
storage = Storage()
kill = KillSwitch(storage)
auth = AuthManager(storage)
admin = AdminManager(storage)
settings_mgr = SettingsManager(storage)
auth.setup_admin_from_env()
settings_mgr.load_into_settings()

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


PUBLIC_PATHS = {"/api/health", "/api/auth/login", "/api/auth/status", "/api/auth/logout", "/api/auth/change-password", "/health"}


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    if path in PUBLIC_PATHS or path.startswith("/ui") or path == "/" or path.startswith("/static"):
        return await call_next(request)
    force_auth = os.getenv("FORCE_AUTH", "").lower() in ("1", "true", "yes")
    auth_disabled = os.getenv("AUTH_DISABLED", "").lower() in ("1", "true", "yes")
    if auth_disabled and not force_auth:
        return await call_next(request)
    # Fail closed: if no admin configured, do not expose data
    if not storage.has_admin():
        return JSONResponse({"error": "setup required"}, status_code=503)
    token = request.cookies.get("session")
    user = auth.validate_session(token)
    if user is None:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    request.state.user = user
    return await call_next(request)


def _auth(request: Request):
    auth_disabled = os.getenv("AUTH_DISABLED", "").lower() in ("1", "true", "yes")
    force_auth = os.getenv("FORCE_AUTH", "").lower() in ("1", "true", "yes")
    if auth_disabled and not force_auth:
        return
    # Prefer session auth when an admin exists
    if storage.has_admin():
        token = request.cookies.get("session")
        user = auth.validate_session(token)
        if user is None:
            raise HTTPException(status_code=401, detail="unauthorized")
        return
    # Legacy token fallback only if configured
    if ADMIN_TOKEN:
        token = request.headers.get("X-Admin-Token") or request.query_params.get("token")
        if token != ADMIN_TOKEN:
            raise HTTPException(status_code=403, detail="forbidden")


@app.get("/health")
def health():
    hb = storage.get_heartbeat()
    last = hb.get("last_beat")
    healthy = last is not None and (time.time() - (last or 0)) < 300
    return {"status": "ok" if healthy else "degraded", "mode": settings.trading_mode,
            "live_authorized": settings.live_authorized, "worker_healthy": healthy}


@app.get("/status")
def status():
    halted, reason = kill.is_halted()
    hb = storage.get_heartbeat()
    last = hb.get("last_beat")
    worker_healthy = last is not None and (time.time() - (last or 0)) < 300
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
        "worker_healthy": worker_healthy,
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


@app.get("/events")
def events(limit: int = 100, agent: str = ""):
    return {"events": storage.recent_events(limit=limit, agent=agent)}


@app.get("/equity")
def equity():
    return {"equity": storage.equity_summary(),
            "simulated_starting_balance": str(settings.simulated_starting_balance),
            "trading_mode": settings.trading_mode}


@app.get("/agents")
def agents():
    evs = storage.recent_events(limit=200)
    latest = {}
    for e in evs:
        if e["agent"] not in latest:
            latest[e["agent"]] = e
    # ensure all seven agents present
    for name in ["SCANNER", "RUG CHECK", "SIZER", "EXECUTER", "LOGGER", "EQUITY", "ADMIN"]:
        latest.setdefault(name, {"agent": name, "status": "IDLE", "reason": "", "ts": None, "event_type": ""})
    return {"agents": list(latest.values())}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    # auth check
    auth_disabled = os.getenv("AUTH_DISABLED", "").lower() in ("1", "true", "yes")
    force_auth = os.getenv("FORCE_AUTH", "").lower() in ("1", "true", "yes")
    if storage.has_admin() and not (auth_disabled and not force_auth):
        token = None
        try:
            token = ws.cookies.get("session")
        except Exception:
            token = None
        if token is None:
            cookie_header = dict(ws.scope.get("headers", [])).get(b"cookie", b"").decode()
            for part in cookie_header.split(";"):
                part = part.strip()
                if part.startswith("session="):
                    token = part.split("=", 1)[1]
        if auth.validate_session(token) is None:
            await ws.close(code=4401)
            return
    await ws.accept()
    last_id = 0
    try:
        while True:
            evs = storage.recent_events(limit=50)
            new = [e for e in evs if (e.get("id") or 0) > last_id]
            if new:
                new_sorted = sorted(new, key=lambda x: x["id"])
                last_id = new_sorted[-1]["id"]
                for e in new_sorted:
                    await ws.send_text(_json.dumps({"type": "event", "data": e}))
            hb = storage.get_heartbeat()
            halted, reason = kill.is_halted()
            await ws.send_text(_json.dumps({"type": "status", "data": {
                "trading_mode": settings.trading_mode,
                "live_authorized": settings.live_authorized,
                "halted": halted,
                "halt_reason": reason,
                "worker_heartbeat": hb,
                "open_positions": len(storage.open_positions()),
                "equity": storage.equity_summary(),
            }}))
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        pass
    except Exception:
        try:
            await ws.close()
        except Exception:
            pass


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


# ---- API v1 (stable) ----
@app.get("/api/health")
@api_error_handler
def api_health():
    hb = storage.get_heartbeat()
    last = hb.get("last_beat")
    healthy = last is not None and (time.time() - (last or 0)) < 300
    return {"status": "ok" if healthy else "degraded", "mode": settings.normalized_mode,
            "live_authorized": settings.live_authorized, "worker_healthy": healthy}


@app.get("/api/status")
@api_error_handler
def api_status():
    halted, reason = kill.is_halted()
    hb = storage.get_heartbeat()
    last = hb.get("last_beat")
    worker_healthy = last is not None and (time.time() - (last or 0)) < 300
    return {
        "health": "ok",
        "trading_mode": settings.normalized_mode,
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
        "worker_healthy": worker_healthy,
        "agent_statuses": storage.get_agent_statuses(),
        "workflow_stage": storage.get_setting("workflow_stage", "idle"),
    }


@app.get("/api/agents")
@api_error_handler
def api_agents():
    statuses = storage.get_agent_statuses()
    # merge latest event info
    evs = storage.recent_events(limit=200)
    latest = {}
    for e in evs:
        if e["agent"] not in latest:
            latest[e["agent"]] = e
    out = []
    for s in statuses:
        e = latest.get(s["name"], {})
        out.append({
            "name": s["name"],
            "status": s["status"] or "IDLE",
            "last_activity": s["last_activity"],
            "last_success": s["last_success"],
            "error_message": s["error_message"] or "",
            "tasks_completed": s["tasks_completed"] or 0,
            "current_activity": s["current_activity"] or (e.get("event_type") or ""),
        })
    # ensure seven
    names = ["SCANNER", "RUG CHECK", "SIZER", "EXECUTER", "LOGGER", "EQUITY", "ADMIN"]
    have = {a["name"] for a in out}
    for n in names:
        if n not in have:
            out.append({"name": n, "status": "IDLE", "last_activity": None, "last_success": None,
                        "error_message": "", "tasks_completed": 0, "current_activity": ""})
    return {"agents": out}


@app.get("/api/account")
@api_error_handler
def api_account():
    # Paper/testnet: simulated; live: would query exchange (not enabled by default)
    return {
        "mode": settings.normalized_mode,
        "simulated_starting_balance": str(settings.simulated_starting_balance),
        "equity": storage.equity_summary(),
    }


@app.get("/api/market")
@api_error_handler
def api_market():
    # Lightweight: return last known signals as market snapshot
    return {"symbol": settings.symbol, "timeframe": settings.timeframe, "signals": storage.recent_events(limit=10, agent="SCANNER")}


@app.get("/api/signals")
@api_error_handler
def api_signals():
    cur = storage.conn.cursor()
    cur.execute("SELECT symbol,direction,timestamp,entry_price,stop_loss,take_profit,accepted,rejection_reason FROM signals ORDER BY id DESC LIMIT 50")
    rows = cur.fetchall()
    cols = ["symbol", "direction", "timestamp", "entry_price", "stop_loss", "take_profit", "accepted", "rejection_reason"]
    return {"signals": [dict(zip(cols, r)) for r in rows]}


@app.get("/api/positions")
@api_error_handler
def api_positions():
    return {"positions": storage.open_positions()}


@app.get("/api/trades")
@api_error_handler
def api_trades():
    cur = storage.conn.cursor()
    cur.execute("SELECT id,symbol,direction,entry_price,stop_loss,take_profit,quantity,status,opened_at,closed_at,realized_pnl,fees FROM trades ORDER BY id DESC LIMIT 50")
    rows = cur.fetchall()
    cols = ["id", "symbol", "direction", "entry_price", "stop_loss", "take_profit", "quantity", "status", "opened_at", "closed_at", "realized_pnl", "fees"]
    return {"trades": [dict(zip(cols, r)) for r in rows]}


@app.get("/api/equity")
@api_error_handler
def api_equity():
    from .equity import EquityAgent
    from .paper_trading import PaperTrader
    pt = PaperTrader(storage)
    summ = pt.account_summary(None)
    prices = {}
    try:
        from .binance_client import BinanceClient
        key, secret = settings.credentials
        testnet = settings.use_testnet or settings.trading_mode != "live"
        c = BinanceClient(api_key=key, api_secret=secret, testnet=testnet)
        c.sync_time()
        for p in storage.open_positions():
            try:
                prices[p["symbol"]] = c.ticker_price(p["symbol"])
            except Exception:
                pass
    except Exception:
        pass
    agent = EquityAgent(storage)
    a = agent.analytics(prices)
    return {"equity": storage.equity_summary(),
            "simulated_starting_balance": str(settings.simulated_starting_balance),
            "trading_mode": settings.normalized_mode,
            "analytics": a,
            "account": summ}


@app.get("/api/logs")
@api_error_handler
def api_logs(limit: int = 100, offset: int = 0, agent: str = "", severity: str = "", event_type: str = "", symbol: str = ""):
    return {"events": storage.recent_events(limit=limit, offset=offset, agent=agent, severity=severity,
                                            event_type=event_type, symbol=symbol),
            "total": storage.count_events(agent=agent, severity=severity, event_type=event_type, symbol=symbol)}


@app.get("/api/logs/summary")
@api_error_handler
def api_logs_summary():
    return {"total": storage.count_events(),
            "by_severity": {s: storage.count_events(severity=s) for s in ["DEBUG","INFO","WARNING","ERROR","CRITICAL"]}}


@app.get("/api/settings")
@api_error_handler
def api_settings():
    return {
        "trading_mode": settings.normalized_mode,
        "broker_enabled": settings.broker_enabled,
        "auto_trade": settings.auto_trade,
        "live_trading_enabled": settings.live_trading_enabled,
        "use_testnet": settings.use_testnet,
        "symbol": settings.symbol,
        "timeframe": settings.timeframe,
        "max_leverage": settings.max_leverage,
        "max_simultaneous_positions": settings.max_simultaneous_positions,
        "max_daily_loss_usdt": str(settings.max_daily_loss_usdt),
        "max_planned_loss_per_trade": str(settings.max_planned_loss_per_trade),
        "simulated_starting_balance": str(settings.simulated_starting_balance),
    }


@app.post("/api/scanner/start")
@api_error_handler
def api_scanner_start(request: Request):
    _auth(request)
    storage.log_event("ADMIN", "", "scanner", "start", "scanner start requested")
    storage.log_admin_action("scanner_start")
    storage.upsert_agent_status("SCANNER", "RUNNING", current_activity="started")
    return {"ok": True}


@app.post("/api/scanner/stop")
@api_error_handler
def api_scanner_stop(request: Request):
    _auth(request)
    storage.log_event("ADMIN", "", "scanner", "stop", "scanner stop requested")
    storage.log_admin_action("scanner_stop")
    storage.upsert_agent_status("SCANNER", "STOPPED", current_activity="stopped")
    return {"ok": True}


@app.post("/api/trading/enable")
@api_error_handler
def api_trading_enable(request: Request):
    _auth(request)
    storage.log_admin_action("trading_enable")
    return {"ok": False, "reason": "Live trading enable requires .env flags and restart; not allowed via API"}


@app.post("/api/trading/disable")
@api_error_handler
def api_trading_disable(request: Request):
    _auth(request)
    kill.halt("trading disabled via API")
    storage.log_admin_action("trading_disable")
    return {"halted": True}


@app.post("/api/system/kill")
@api_error_handler
def api_system_kill(request: Request):
    _auth(request)
    kill.halt("emergency kill via API")
    storage.log_admin_action("emergency_kill")
    return {"halted": True}


@app.websocket("/api/ws")
async def api_websocket(ws: WebSocket):
    auth_disabled = os.getenv("AUTH_DISABLED", "").lower() in ("1", "true", "yes")
    force_auth = os.getenv("FORCE_AUTH", "").lower() in ("1", "true", "yes")
    if storage.has_admin() and not (auth_disabled and not force_auth):
        token = None
        try:
            token = ws.cookies.get("session")
        except Exception:
            token = None
        if token is None:
            cookie_header = dict(ws.scope.get("headers", [])).get(b"cookie", b"").decode()
            for part in cookie_header.split(";"):
                part = part.strip()
                if part.startswith("session="):
                    token = part.split("=", 1)[1]
        if auth.validate_session(token) is None:
            await ws.close(code=4401)
            return
    await ws.accept()
    last_id = 0
    try:
        while True:
            evs = storage.recent_events(limit=50)
            new = [e for e in evs if (e.get("id") or 0) > last_id]
            if new:
                new_sorted = sorted(new, key=lambda x: x["id"])
                last_id = new_sorted[-1]["id"]
                for e in new_sorted:
                    await ws.send_text(_json.dumps({"type": "event", "data": e}))
            hb = storage.get_heartbeat()
            halted, reason = kill.is_halted()
            await ws.send_text(_json.dumps({"type": "status", "data": {
                "trading_mode": settings.normalized_mode,
                "live_authorized": settings.live_authorized,
                "halted": halted,
                "halt_reason": reason,
                "worker_heartbeat": hb,
                "open_positions": len(storage.open_positions()),
                "equity": storage.equity_summary(),
                "agents": storage.get_agent_statuses(),
            }}))
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        pass
    except Exception:
        try:
            await ws.close()
        except Exception:
            pass


@app.get("/api/scanner/symbols")
@api_error_handler
def api_scanner_symbols():
    if getattr(settings, "scan_all_usdt_perpetuals", True):
        symbols = storage.get_market_universe()
        if symbols:
            return {"symbols": symbols, "count": len(symbols), "mode": "all_usdt_perpetuals"}
    return {"symbols": settings.symbol_list, "count": len(settings.symbol_list), "mode": "manual"}


@app.get("/api/market-data/status")
@api_error_handler
def api_market_data_status():
    return storage.market_data_summary()


@app.put("/api/scanner/symbols")
@api_error_handler
async def api_scanner_symbols_put(request: Request):
    _auth(request)
    data = await request.json()
    syms = data.get("symbols", [])
    if not isinstance(syms, list):
        return JSONResponse({"error": "symbols must be list"}, status_code=400)
    syms = [str(s).strip().upper() for s in syms if str(s).strip()]
    settings.symbols = ",".join(syms)
    storage.set_setting("scanner_symbols", ",".join(syms))
    storage.log_admin_action("scanner_symbols_update", details=",".join(syms))
    return {"symbols": syms}


@app.post("/api/scanner/symbols")
@api_error_handler
async def api_scanner_symbols_set(request: Request):
    _auth(request)
    data = await request.json()
    syms = data.get("symbols", [])
    if not isinstance(syms, list):
        return JSONResponse({"error": "symbols must be list"}, status_code=400)
    syms = [str(s).strip().upper() for s in syms if str(s).strip()]
    settings.symbols = ",".join(syms)
    storage.set_setting("scanner_symbols", ",".join(syms))
    storage.log_admin_action("scanner_symbols_update", details=",".join(syms))
    return {"symbols": syms}


@app.get("/api/scanner/results")
@api_error_handler
def api_scanner_results(limit: int = 50, symbol: str = ""):
    return {"results": storage.recent_scanner_results(limit=limit, symbol=symbol)}


@app.get("/api/diagnostics")
@api_error_handler
def api_diagnostics(limit: int = 50, symbol: str = "", signals_only: bool = False):
    return {"diagnostics": storage.recent_diagnostics(limit=limit, symbol=symbol or None, signals_only=signals_only)}


@app.get("/api/diagnostics/summary")
@api_error_handler
def api_diagnostics_summary():
    return storage.diagnostics_summary()


@app.get("/api/rug-check/{symbol}")
@api_error_handler
def api_rug_check(symbol: str):
    from .scanner import Scanner
    from .binance_client import BinanceClient
    # build client
    key, secret = settings.credentials
    testnet = settings.use_testnet or settings.trading_mode != "live"
    client = BinanceClient(api_key=key, api_secret=secret, testnet=testnet)
    try:
        client.sync_time()
    except Exception:
        pass
    try:
        kl = client.klines(symbol.upper(), settings.timeframe, 200)
    except Exception as e:
        return {"symbol": symbol.upper(), "error": str(e)}
    from .rug_check import RugChecker
    risk = RugChecker().assess(symbol.upper(), kl)
    storage.save_risk_assessment(symbol.upper(), risk["risk_rating"], risk["reasons"], risk["warnings"], risk["metrics"])
    return risk


@app.post("/api/rug-check/scan")
@api_error_handler
async def api_rug_check_scan(request: Request):
    _auth(request)
    from .binance_client import BinanceClient
    key, secret = settings.credentials
    testnet = settings.use_testnet or settings.trading_mode != "live"
    client = BinanceClient(api_key=key, api_secret=secret, testnet=testnet)
    try:
        client.sync_time()
    except Exception:
        pass
    from .rug_check import RugChecker
    out = []
    for sym in settings.symbol_list:
        try:
            kl = client.klines(sym, settings.timeframe, 200)
            risk = RugChecker().assess(sym, kl)
            storage.save_risk_assessment(sym, risk["risk_rating"], risk["reasons"], risk["warnings"], risk["metrics"])
            out.append(risk)
        except Exception as e:
            out.append({"symbol": sym, "error": str(e)})
    storage.log_admin_action("rug_check_scan")
    return {"results": out}


@app.get("/api/sizer/config")
@api_error_handler
def api_sizer_config():
    return {
        "risk_per_trade_pct": str(settings.risk_per_trade_pct),
        "max_daily_loss_pct": str(settings.max_daily_loss_pct),
        "max_leverage": settings.max_leverage,
        "max_simultaneous_positions": settings.max_simultaneous_positions,
        "max_planned_loss_per_trade": str(settings.max_planned_loss_per_trade),
        "estimated_maker_fee": str(settings.estimated_maker_fee),
        "estimated_taker_fee": str(settings.estimated_taker_fee),
        "estimated_slippage": str(settings.estimated_slippage),
        "min_reward_to_risk": str(settings.min_reward_to_risk),
    }


@app.put("/api/sizer/config")
@api_error_handler
async def api_sizer_config_update(request: Request):
    _auth(request)
    data = await request.json()
    if "risk_per_trade_pct" in data:
        settings.risk_per_trade_pct = __import__("decimal").Decimal(str(data["risk_per_trade_pct"]))
    if "max_daily_loss_pct" in data:
        settings.max_daily_loss_pct = __import__("decimal").Decimal(str(data["max_daily_loss_pct"]))
    storage.set_setting("risk_per_trade_pct", str(settings.risk_per_trade_pct))
    storage.set_setting("max_daily_loss_pct", str(settings.max_daily_loss_pct))
    storage.log_admin_action("sizer_config_update", details=str(data))
    return {"ok": True}


@app.post("/api/sizer/calculate")
@api_error_handler
async def api_sizer_calculate(request: Request):
    data = await request.json()
    from .sizer import Sizer
    from decimal import Decimal
    sizer = Sizer()
    kill_halted, _ = kill.is_halted()
    dd = sizer.calculate(
        symbol=data.get("symbol", settings.symbol),
        direction=data.get("direction", "LONG"),
        entry_price=data.get("entry_price", "0"),
        stop_loss_price=data.get("stop_loss_price", "0"),
        take_profit_price=data.get("take_profit_price", "0"),
        available_equity=data.get("available_equity", str(settings.simulated_starting_balance)),
        rug_rating=data.get("rug_rating", "LOW"),
        kill_halted=kill_halted,
        daily_loss_used=kill.daily_loss_used(),
        open_positions_count=len(storage.open_positions()),
        exchange_info=None,
    )
    storage.log_event("SIZER", data.get("symbol", settings.symbol), "calculate", "approved" if dd.approved else "rejected", dd.reason)
    storage.upsert_agent_status("SIZER", "ANALYZING" if dd.approved else "ERROR", current_activity=dd.reason, last_success=dd.approved, error_message="" if dd.approved else dd.reason)
    return {
        "approved": dd.approved,
        "reason": dd.reason,
        "quantity": str(dd.quantity),
        "risk_amount": str(dd.risk_amount),
        "estimated_loss": str(dd.estimated_loss),
        "estimated_fees": str(dd.estimated_fees),
        "margin_required": str(dd.margin_required),
        "notional": str(dd.notional),
        "reward_to_risk": str(dd.reward_to_risk),
    }


@app.get("/api/paper/account")
@api_error_handler
def api_paper_account():
    from .paper_trading import PaperTrader
    from .binance_client import BinanceClient
    pt = PaperTrader(storage)
    client = None
    try:
        key, secret = settings.credentials
        testnet = settings.use_testnet or settings.trading_mode != "live"
        c = BinanceClient(api_key=key, api_secret=secret, testnet=testnet)
        c.sync_time()
        client = c
    except Exception:
        client = None
    return pt.account_summary(client)


@app.get("/api/paper/positions")
@api_error_handler
def api_paper_positions():
    from .paper_trading import PaperTrader
    from .binance_client import BinanceClient
    pt = PaperTrader(storage)
    client = None
    try:
        key, secret = settings.credentials
        testnet = settings.use_testnet or settings.trading_mode != "live"
        c = BinanceClient(api_key=key, api_secret=secret, testnet=testnet)
        c.sync_time()
        client = c
    except Exception:
        client = None
    positions = storage.open_positions()
    # attach current price if available
    out = []
    for p in positions:
        price = None
        if client is not None:
            try:
                price = client.ticker_price(p["symbol"])
            except Exception:
                price = None
        out.append({**p, "current_price": (str(price) if price is not None else None)})
    return {"positions": out}


@app.get("/api/paper/trades")
@api_error_handler
def api_paper_trades():
    cur = storage.conn.cursor()
    cur.execute("SELECT id,symbol,direction,entry_price,stop_loss,take_profit,quantity,status,opened_at,closed_at,realized_pnl,fees FROM trades ORDER BY id DESC LIMIT 50")
    rows = cur.fetchall()
    cols = ["id", "symbol", "direction", "entry_price", "stop_loss", "take_profit", "quantity", "status", "opened_at", "closed_at", "realized_pnl", "fees"]
    return {"trades": [dict(zip(cols, r)) for r in rows]}


@app.post("/api/paper/execute")
@api_error_handler
async def api_paper_execute(request: Request):
    data = await request.json()
    from .paper_trading import PaperTrader
    from .sizer import Sizer
    from .binance_client import BinanceClient
    from decimal import Decimal
    pt = PaperTrader(storage)
    kill_halted, _ = kill.is_halted()
    if kill_halted:
        return JSONResponse({"ok": False, "reason": "kill switch halted"}, status_code=400)
    if storage.open_positions():
        return JSONResponse({"ok": False, "reason": "position already open"}, status_code=400)
    sizer = Sizer()
    dd = sizer.calculate(
        symbol=data.get("symbol", settings.symbol),
        direction=data.get("direction", "LONG"),
        entry_price=data.get("entry_price", "0"),
        stop_loss_price=data.get("stop_loss_price", "0"),
        take_profit_price=data.get("take_profit_price", "0"),
        available_equity=data.get("available_equity", str(settings.simulated_starting_balance)),
        rug_rating=data.get("rug_rating", "LOW"),
        kill_halted=kill_halted,
        daily_loss_used=kill.daily_loss_used(),
        open_positions_count=len(storage.open_positions()),
        exchange_info=None,
    )
    storage.log_event("SIZER", data.get("symbol", settings.symbol), "calculate", "approved" if dd.approved else "rejected", dd.reason)
    if not dd.approved:
        storage.upsert_agent_status("SIZER", "ERROR", current_activity=dd.reason, error_message=dd.reason)
        return JSONResponse({"ok": False, "reason": dd.reason}, status_code=400)
    storage.upsert_agent_status("SIZER", "ANALYZING", current_activity="approved", last_success=True)
    # build proposal dict
    proposal = {
        "symbol": data.get("symbol", settings.symbol),
        "direction": data.get("direction", "LONG"),
        "entry_price": data.get("entry_price", "0"),
        "stop_loss": data.get("stop_loss_price", "0"),
        "take_profit": data.get("take_profit_price", "0"),
    }
    client = None
    try:
        key, secret = settings.credentials
        testnet = settings.use_testnet or settings.trading_mode != "live"
        c = BinanceClient(api_key=key, api_secret=secret, testnet=testnet)
        c.sync_time()
        client = c
    except Exception:
        client = None
    # fallback client for prices: use mock? If none, pass a dummy? PaperTrader needs client for price; if None, entry uses proposal price
    class _Dummy:
        def ticker_price(self, s):
            return None
    res = pt.open_position(client if client else _Dummy(), proposal, dd, None)
    if res.get("ok"):
        storage.upsert_agent_status("EXECUTER", "EXECUTING", current_activity="paper position opened", last_success=True)
    else:
        storage.upsert_agent_status("EXECUTER", "ERROR", current_activity=res.get("reason", "failed"), error_message=res.get("reason", ""))
    return res


@app.post("/api/paper/close/{trade_id}")
@api_error_handler
async def api_paper_close(trade_id: int, request: Request):
    data = {}
    try:
        data = await request.json()
    except Exception:
        data = {}
    from .paper_trading import PaperTrader
    from .binance_client import BinanceClient
    pt = PaperTrader(storage)
    price = data.get("price")
    if price is None:
        # fetch market price
        # find trade
        positions = storage.open_positions()
        trade = next((p for p in positions if p["id"] == trade_id), None)
        if trade:
            try:
                key, secret = settings.credentials
                testnet = settings.use_testnet or settings.trading_mode != "live"
                c = BinanceClient(api_key=key, api_secret=secret, testnet=testnet)
                c.sync_time()
                price = c.ticker_price(trade["symbol"])
            except Exception:
                price = trade["entry_price"]
    if price is None:
        return JSONResponse({"ok": False, "reason": "price unavailable"}, status_code=400)
    res = pt.close_position(trade_id, price, data.get("reason", "manual"))
    storage.log_event("EXECUTER", "", "paper_close", "closed" if res.get("ok") else "error", str(res))
    return res


@app.get("/api/equity")
@api_error_handler
def api_equity_full():
    from .equity import EquityAgent
    from .paper_trading import PaperTrader
    pt = PaperTrader(storage)
    summ = pt.account_summary(None)
    prices = {}
    # best-effort prices
    try:
        from .binance_client import BinanceClient
        key, secret = settings.credentials
        testnet = settings.use_testnet or settings.trading_mode != "live"
        c = BinanceClient(api_key=key, api_secret=secret, testnet=testnet)
        c.sync_time()
        for p in storage.open_positions():
            try:
                prices[p["symbol"]] = c.ticker_price(p["symbol"])
            except Exception:
                pass
    except Exception:
        pass
    agent = EquityAgent(storage)
    a = agent.analytics(prices)
    return {"account": summ, "analytics": a}


@app.get("/api/equity/history")
@api_error_handler
def api_equity_history(limit: int = 200):
    from .equity import EquityAgent
    agent = EquityAgent(storage)
    return {"history": agent.history(limit=limit)}


@app.get("/api/equity/analytics")
@api_error_handler
def api_equity_analytics():
    from .equity import EquityAgent
    from .paper_trading import PaperTrader
    pt = PaperTrader(storage)
    summ = pt.account_summary(None)
    prices = {}
    try:
        from .binance_client import BinanceClient
        key, secret = settings.credentials
        testnet = settings.use_testnet or settings.trading_mode != "live"
        c = BinanceClient(api_key=key, api_secret=secret, testnet=testnet)
        c.sync_time()
        for p in storage.open_positions():
            try:
                prices[p["symbol"]] = c.ticker_price(p["symbol"])
            except Exception:
                pass
    except Exception:
        pass
    agent = EquityAgent(storage)
    return {"analytics": agent.analytics(prices)}


@app.get("/api/equity/drawdown")
@api_error_handler
def api_equity_drawdown(limit: int = 500):
    from .equity import EquityAgent
    agent = EquityAgent(storage)
    return {"series": agent.drawdown_series(limit=limit)}


# Auth endpoints
@app.post("/api/auth/login")
@api_error_handler
async def api_auth_login(request: Request):
    data = await request.json()
    username = data.get("username", "")
    password = data.get("password", "")
    ip = request.client.host if request.client else "unknown"
    if auth.is_rate_limited(ip):
        return JSONResponse({"error": "rate limited"}, status_code=429)
    ok, token, must_change = auth.login(username, password, ip)
    if not ok:
        return JSONResponse({"error": "invalid credentials"}, status_code=401)
    response = JSONResponse({"ok": True, "must_change_password": must_change})
    secure = os.getenv("COOKIE_SECURE", "").lower() in ("1", "true", "yes")
    response.set_cookie("session", token, httponly=True, samesite="lax", secure=secure, max_age=auth.session_ttl)
    auth.clear_failures(ip)
    storage.log_event("ADMIN", "", "auth", "login", f"user={username}")
    return response


@app.post("/api/auth/logout")
@api_error_handler
def api_auth_logout(request: Request):
    token = request.cookies.get("session")
    auth.logout(token)
    response = JSONResponse({"ok": True})
    response.delete_cookie("session")
    return response


@app.get("/api/auth/status")
@api_error_handler
def api_auth_status(request: Request):
    token = request.cookies.get("session")
    user = auth.validate_session(token)
    must_change = False
    if user:
        u = storage.get_user(user)
        must_change = bool(u and u.get("must_change_password"))
    return {"authenticated": user is not None, "username": user, "must_change_password": must_change,
            "setup_required": not storage.has_admin()}


@app.post("/api/auth/change-password")
@api_error_handler
async def api_auth_change_password(request: Request):
    token = request.cookies.get("session")
    user = auth.validate_session(token)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    data = await request.json()
    new_pw = data.get("new_password", "")
    if len(new_pw) < 8:
        return JSONResponse({"error": "password too short"}, status_code=400)
    auth.change_password(user, new_pw)
    storage.log_event("ADMIN", "", "auth", "password_changed", f"user={user}")
    return {"ok": True}


# Admin endpoints
@app.get("/api/admin/status")
@api_error_handler
def api_admin_status(request: Request):
    token = request.cookies.get("session")
    user = auth.validate_session(token)
    if user is None and storage.has_admin():
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    return admin.overview({"trading_mode": settings.normalized_mode, "live_authorized": settings.live_authorized})


@app.get("/api/admin/actions")
@api_error_handler
def api_admin_actions(request: Request, limit: int = 50):
    token = request.cookies.get("session")
    user = auth.validate_session(token)
    if user is None and storage.has_admin():
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    return {"actions": storage.recent_admin_actions(limit=limit)}


@app.get("/api/admin/settings")
@api_error_handler
def api_admin_settings_get(request: Request):
    token = request.cookies.get("session")
    user = auth.validate_session(token)
    if user is None and storage.has_admin():
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    return settings_mgr.get_all()


@app.put("/api/admin/settings")
@api_error_handler
async def api_admin_settings_put(request: Request):
    token = request.cookies.get("session")
    user = auth.validate_session(token)
    if user is None and storage.has_admin():
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    data = await request.json()
    res = settings_mgr.validate_and_set(data)
    storage.log_event("ADMIN", "", "settings", "update", str(res))
    return res


@app.post("/api/admin/agents/{name}/start")
@api_error_handler
def api_admin_agent_start(name: str, request: Request):
    token = request.cookies.get("session")
    user = auth.validate_session(token)
    if user is None and storage.has_admin():
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    storage.upsert_agent_status(name.upper(), "RUNNING", current_activity="started via admin")
    admin.record_action("agent_start", actor=user or "admin", details=name)
    return {"ok": True}


@app.post("/api/admin/agents/{name}/stop")
@api_error_handler
def api_admin_agent_stop(name: str, request: Request):
    token = request.cookies.get("session")
    user = auth.validate_session(token)
    if user is None and storage.has_admin():
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    storage.upsert_agent_status(name.upper(), "STOPPED", current_activity="stopped via admin")
    admin.record_action("agent_stop", actor=user or "admin", details=name)
    return {"ok": True}


@app.get("/api/monitoring")
@api_error_handler
def api_monitoring():
    import shutil, os as _os
    hb = storage.get_heartbeat()
    last_beat = hb.get("last_beat")
    hb_age = (time.time() - last_beat) if last_beat else None
    # market data freshness from last scanner event
    evs = storage.recent_events(limit=1, agent="SCANNER")
    last_scan = evs[0]["ts"] if evs else None
    scan_age = (time.time() - last_scan) if last_scan else None
    disk = None
    try:
        du = shutil.disk_usage(".")
        disk = {"total": du.total, "used": du.used, "free": du.free}
    except Exception:
        disk = None
    db_size = None
    try:
        db_size = _os.path.getsize(storage.path)
    except Exception:
        db_size = None
    return {
        "worker_heartbeat_age_seconds": hb_age,
        "last_scan_age_seconds": scan_age,
        "disk": disk,
        "db_size_bytes": db_size,
        "open_positions": len(storage.open_positions()),
        "events_count": storage.count_events(),
    }


@app.get("/", response_class=HTMLResponse)
def index():
    ui_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ui", "index.html")
    if os.path.exists(ui_path):
        return FileResponse(ui_path)
    return HTMLResponse("<h1>Binance Signal Engine</h1><p>UI not found.</p>")