"""FastAPI dashboard exposing status. Binds to localhost by default."""
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from .config import settings
from .storage import Storage
from .kill_switch import KillSwitch

app = FastAPI(title="Binance Signal Engine Status")
storage = Storage()
kill = KillSwitch(storage)


@app.get("/health")
def health():
    return {"status": "ok", "mode": settings.trading_mode, "live_authorized": settings.live_authorized}


@app.get("/status")
def status():
    halted, reason = kill.is_halted()
    return {
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
    }


@app.post("/halt")
def halt():
    kill.halt("manual halt via dashboard")
    return {"halted": True}


@app.post("/resume")
def resume():
    kill.reset(operator_confirmed=True)
    return {"halted": False}