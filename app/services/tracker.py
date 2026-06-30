import time
from typing import Dict, List, Optional
from datetime import datetime, timezone

from app.services import database as db


def create_trade(pair: str, signal_type: str, entry: float, sl: float,
                 tp1: float, tp2: float, tp3: float, confidence: int,
                 entry_limit: Optional[float] = None) -> Dict:
    now = datetime.now(timezone.utc).isoformat()
    trade = {
        "id": f"{pair}_{int(time.time())}",
        "pair": pair,
        "type": signal_type,
        "entry": entry,
        "entry_limit": entry_limit,
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "confidence": confidence,
        "status": "OPEN",
        "created_at": now,
        "updated_at": now,
        "closed_at": None,
        "pnl_pct": None,
        "remarks": None,
        "updates": 0,
        "quantity": None,
        "execution_mode": None,
        "order_id": None,
        "simulated": False
    }
    return trade


def add_trade(trade: Dict):
    db.insert_trade(trade)
    _sync_to_redis()


def load_trades() -> List[Dict]:
    return db.list_trades()


def get_open_trades() -> List[Dict]:
    return db.get_open_trades()


def get_closed_trades() -> List[Dict]:
    return db.get_closed_trades()


def update_trade(trade_id: str, current_price: float) -> Optional[Dict]:
    trade = db.get_trade(trade_id)
    if not trade or trade["status"] != "OPEN":
        return None

    signal_type = trade["type"]
    entry = trade["entry"]
    sl = trade["sl"]
    tp1 = trade["tp1"] or 0
    tp2 = trade["tp2"] or 0
    tp3 = trade["tp3"] or 0

    closed = False
    remarks = None
    pnl_pct = 0
    new_status = "OPEN"

    if signal_type == "BUY":
        if current_price <= sl:
            new_status = "SL"
            closed = True
            remarks = "SL Hit"
            pnl_pct = round((sl - entry) / entry * 100, 2)
        elif current_price >= tp3:
            new_status = "TP3"
            closed = True
            remarks = "TP3 Hit"
            pnl_pct = round((tp3 - entry) / entry * 100, 2)
        elif current_price >= tp2:
            new_status = "TP2"
            closed = True
            remarks = "TP2 Hit"
            pnl_pct = round((tp2 - entry) / entry * 100, 2)
        elif current_price >= tp1:
            new_status = "TP1"
            closed = True
            remarks = "TP1 Hit"
            pnl_pct = round((tp1 - entry) / entry * 100, 2)
    elif signal_type == "SELL":
        if current_price >= sl:
            new_status = "SL"
            closed = True
            remarks = "SL Hit"
            pnl_pct = round((entry - sl) / entry * 100, 2)
        elif current_price <= tp3:
            new_status = "TP3"
            closed = True
            remarks = "TP3 Hit"
            pnl_pct = round((entry - tp3) / entry * 100, 2)
        elif current_price <= tp2:
            new_status = "TP2"
            closed = True
            remarks = "TP2 Hit"
            pnl_pct = round((entry - tp2) / entry * 100, 2)
        elif current_price <= tp1:
            new_status = "TP1"
            closed = True
            remarks = "TP1 Hit"
            pnl_pct = round((entry - tp1) / entry * 100, 2)

    now = datetime.now(timezone.utc).isoformat()
    updates = {
        "status": new_status,
        "updated_at": now,
        "updates": trade.get("updates", 0) + 1
    }

    if closed:
        updates["closed_at"] = now
        updates["pnl_pct"] = pnl_pct
        updates["remarks"] = remarks

    db.update_trade_by_id(trade_id, updates)
    _sync_to_redis()

    trade.update(updates)
    return trade


def close_trade_manually(trade_id: str, remarks: str, close_price: float) -> Optional[Dict]:
    trade = db.get_trade(trade_id)
    if not trade or trade["status"] != "OPEN":
        return None

    entry = trade["entry"]
    if trade["type"] == "BUY":
        pnl = round((close_price - entry) / entry * 100, 2)
    else:
        pnl = round((entry - close_price) / entry * 100, 2)

    now = datetime.now(timezone.utc).isoformat()
    updates = {
        "status": "MANUAL_CLOSE",
        "closed_at": now,
        "pnl_pct": pnl,
        "remarks": remarks,
        "updated_at": now
    }

    db.update_trade_by_id(trade_id, updates)
    _sync_to_redis()

    trade.update(updates)
    return trade


def remove_trade(trade_id: str):
    db.delete_trade(trade_id)
    _sync_to_redis()


def get_analytics() -> Dict:
    return db.get_analytics()


def _sync_to_redis():
    try:
        from app.services import redis_client as rc
        if rc.r:
            trades = db.list_trades()
            import json
            rc.r.set("trades:all", json.dumps(trades), ex=86400)
    except Exception:
        pass
