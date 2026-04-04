import time
import json
import os
from typing import Dict, List, Optional
from datetime import datetime

TRADES_FILE = "trades.json"

def load_trades() -> List[Dict]:
    if os.path.exists(TRADES_FILE):
        try:
            with open(TRADES_FILE, 'r') as f:
                return json.load(f)
        except:
            return []
    return []

def save_trades(trades: List[Dict]):
    with open(TRADES_FILE, 'w') as f:
        json.dump(trades, f, indent=2)

def create_trade(pair: str, signal_type: str, entry: float, sl: float, 
                 tp1: float, tp2: float, tp3: float, confidence: int,
                 entry_limit: Optional[float] = None) -> Dict:
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
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
        "closed_at": None,
        "pnl_pct": None,
        "remarks": None,
        "updates": 0
    }
    return trade

def add_trade(trade: Dict):
    trades = load_trades()
    trades.append(trade)
    save_trades(trades)

def update_trade(trade_id: str, current_price: float) -> Optional[Dict]:
    trades = load_trades()
    
    for trade in trades:
        if trade["id"] == trade_id and trade["status"] == "OPEN":
            signal_type = trade["type"]
            entry = trade["entry"]
            sl = trade["sl"]
            tp1 = trade["tp1"]
            tp2 = trade["tp2"]
            tp3 = trade["tp3"]
            
            closed = False
            remarks = None
            pnl_pct = 0
            
            if signal_type == "BUY":
                if current_price <= sl:
                    trade["status"] = "SL"
                    closed = True
                    remarks = "SL Hit"
                    pnl_pct = round((sl - entry) / entry * 100, 2)
                elif current_price >= tp3:
                    trade["status"] = "TP3"
                    closed = True
                    remarks = "TP3 Hit"
                    pnl_pct = round((tp3 - entry) / entry * 100, 2)
                elif current_price >= tp2:
                    trade["status"] = "TP2"
                    closed = True
                    remarks = "TP2 Hit"
                    pnl_pct = round((tp2 - entry) / entry * 100, 2)
                elif current_price >= tp1:
                    trade["status"] = "TP1"
                    closed = True
                    remarks = "TP1 Hit"
                    pnl_pct = round((tp1 - entry) / entry * 100, 2)
            elif signal_type == "SELL":
                if current_price >= sl:
                    trade["status"] = "SL"
                    closed = True
                    remarks = "SL Hit"
                    pnl_pct = round((entry - sl) / entry * 100, 2)
                elif current_price <= tp3:
                    trade["status"] = "TP3"
                    closed = True
                    remarks = "TP3 Hit"
                    pnl_pct = round((entry - tp3) / entry * 100, 2)
                elif current_price <= tp2:
                    trade["status"] = "TP2"
                    closed = True
                    remarks = "TP2 Hit"
                    pnl_pct = round((entry - tp2) / entry * 100, 2)
                elif current_price <= tp1:
                    trade["status"] = "TP1"
                    closed = True
                    remarks = "TP1 Hit"
                    pnl_pct = round((entry - tp1) / entry * 100, 2)
            
            if closed:
                trade["closed_at"] = datetime.utcnow().isoformat()
                trade["pnl_pct"] = pnl_pct
                trade["remarks"] = remarks
            
            trade["updated_at"] = datetime.utcnow().isoformat()
            trade["updates"] = trade.get("updates", 0) + 1
            
            save_trades(trades)
            return trade
    
    return None

def get_open_trades() -> List[Dict]:
    trades = load_trades()
    return [t for t in trades if t["status"] == "OPEN"]

def get_closed_trades() -> List[Dict]:
    trades = load_trades()
    return [t for t in trades if t["status"] != "OPEN"]

def get_analytics() -> Dict:
    trades = load_trades()
    closed = [t for t in trades if t["status"] != "OPEN"]
    
    if not closed:
        return {
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0,
            "avg_win": 0,
            "avg_loss": 0,
            "tp1_hits": 0,
            "tp2_hits": 0,
            "tp3_hits": 0,
            "sl_hits": 0,
            "avg_rr": 0,
            "total_pnl": 0
        }
    
    wins = [t for t in closed if t.get("pnl_pct", 0) > 0]
    losses = [t for t in closed if t.get("pnl_pct", 0) <= 0]
    
    tp1_hits = len([t for t in closed if t.get("status") == "TP1"])
    tp2_hits = len([t for t in closed if t.get("status") == "TP2"])
    tp3_hits = len([t for t in closed if t.get("status") == "TP3"])
    sl_hits = len([t for t in closed if t.get("status") == "SL"])
    
    avg_win = sum([t["pnl_pct"] for t in wins]) / len(wins) if wins else 0
    avg_loss = abs(sum([t["pnl_pct"] for t in losses]) / len(losses)) if losses else 0
    avg_rr = avg_win / avg_loss if avg_loss > 0 else 0
    
    return {
        "total_trades": len(closed),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / len(closed) * 100, 2) if closed else 0,
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "tp1_hits": tp1_hits,
        "tp2_hits": tp2_hits,
        "tp3_hits": tp3_hits,
        "sl_hits": sl_hits,
        "avg_rr": round(avg_rr, 2),
        "total_pnl": round(sum([t.get("pnl_pct", 0) for t in closed]), 2),
        "open_trades": len([t for t in trades if t["status"] == "OPEN"])
    }

def remove_trade(trade_id: str):
    trades = load_trades()
    trades = [t for t in trades if t["id"] != trade_id]
    save_trades(trades)

def close_trade_manually(trade_id: str, remarks: str, close_price: float):
    trades = load_trades()
    
    for trade in trades:
        if trade["id"] == trade_id and trade["status"] == "OPEN":
            entry = trade["entry"]
            if trade["type"] == "BUY":
                pnl = round((close_price - entry) / entry * 100, 2)
            else:
                pnl = round((entry - close_price) / entry * 100, 2)
            
            trade["status"] = "MANUAL_CLOSE"
            trade["closed_at"] = datetime.utcnow().isoformat()
            trade["pnl_pct"] = pnl
            trade["remarks"] = remarks
            trade["updated_at"] = datetime.utcnow().isoformat()
            
            save_trades(trades)
            return trade
    
    return None

def load_trades_from_file():
    return load_trades()