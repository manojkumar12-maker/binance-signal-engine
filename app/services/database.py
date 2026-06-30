import sqlite3
import threading
import time
import os
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

DB_PATH = os.environ.get("DATABASE_URL", "sqlite:///trades.db")
if DB_PATH.startswith("sqlite:///"):
    DB_FILE = DB_PATH[len("sqlite:///"):]
else:
    DB_FILE = "trades.db"

_local = threading.local()
_write_lock = threading.Lock()
_db_initialized = False

SCHEMA_VERSION = 1

MIGRATIONS = {
    1: """
        CREATE TABLE IF NOT EXISTS trades (
            id TEXT PRIMARY KEY,
            pair TEXT NOT NULL,
            type TEXT NOT NULL CHECK(type IN ('BUY', 'SELL')),
            entry REAL NOT NULL,
            entry_limit REAL,
            sl REAL NOT NULL,
            tp1 REAL,
            tp2 REAL,
            tp3 REAL,
            confidence INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'OPEN'
                CHECK(status IN ('OPEN','TP1','TP2','TP3','SL','MANUAL_CLOSE','CANCELLED','BUST')),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            closed_at TEXT,
            pnl_pct REAL,
            remarks TEXT,
            updates INTEGER NOT NULL DEFAULT 0,
            quantity REAL,
            execution_mode TEXT,
            order_id TEXT,
            simulated INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
        CREATE INDEX IF NOT EXISTS idx_trades_pair ON trades(pair);
        CREATE INDEX IF NOT EXISTS idx_trades_created ON trades(created_at);
        CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY);
        INSERT INTO schema_version (version) VALUES (1);
    """
}


def _get_conn() -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(DB_FILE, timeout=30, check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA busy_timeout=5000")
        _local.conn.execute("PRAGMA synchronous=NORMAL")
        _local.conn.execute("PRAGMA foreign_keys=ON")
    return _local.conn


def _execute(sql: str, params: tuple = ()) -> sqlite3.Cursor:
    conn = _get_conn()
    return conn.execute(sql, params)


def _commit():
    conn = _get_conn()
    conn.commit()


def init_db():
    global _db_initialized
    if _db_initialized:
        return

    with _write_lock:
        conn = _get_conn()
        cursor = conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='schema_version'")
        has_schema = cursor.fetchone()[0] > 0

        if not has_schema:
            logger.info("[DB] Initializing schema...")
            for ver in sorted(MIGRATIONS.keys()):
                conn.executescript(MIGRATIONS[ver])
            conn.commit()
            logger.info("[DB] Schema initialized at version %d", max(MIGRATIONS.keys()))
        else:
            row = conn.execute("SELECT max(version) FROM schema_version").fetchone()
            current_ver = row[0] if row and row[0] else 0
            for ver in sorted(MIGRATIONS.keys()):
                if ver > current_ver:
                    logger.info("[DB] Migrating to version %d...", ver)
                    conn.executescript(MIGRATIONS[ver])
                    conn.execute("INSERT INTO schema_version (version) VALUES (?)", (ver,))
                    conn.commit()
                    logger.info("[DB] Migrated to version %d", ver)

    _db_initialized = True
    logger.info("[DB] Ready at %s (WAL mode)", DB_FILE)


def close_db():
    if hasattr(_local, "conn") and _local.conn:
        _local.conn.close()
        _local.conn = None


def insert_trade(trade: Dict) -> bool:
    with _write_lock:
        try:
            _execute("""
                INSERT INTO trades (id, pair, type, entry, entry_limit, sl, tp1, tp2, tp3,
                    confidence, status, created_at, updated_at, closed_at, pnl_pct,
                    remarks, updates, quantity, execution_mode, order_id, simulated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trade["id"], trade["pair"], trade["type"], trade["entry"],
                trade.get("entry_limit"), trade["sl"],
                trade.get("tp1"), trade.get("tp2"), trade.get("tp3"),
                trade["confidence"], trade["status"],
                trade["created_at"], trade["updated_at"],
                trade.get("closed_at"), trade.get("pnl_pct"),
                trade.get("remarks"), trade.get("updates", 0),
                trade.get("quantity"), trade.get("execution_mode"),
                trade.get("order_id"), 1 if trade.get("simulated") else 0
            ))
            _commit()
            return True
        except Exception as e:
            logger.error("[DB] insert_trade failed: %s", e)
            return False


def update_trade_by_id(trade_id: str, updates: Dict) -> bool:
    with _write_lock:
        try:
            sets = []
            params = []
            for key, val in updates.items():
                sets.append(f"{key} = ?")
                params.append(val)
            params.append(trade_id)
            _execute(f"UPDATE trades SET {', '.join(sets)} WHERE id = ?", tuple(params))
            _commit()
            return True
        except Exception as e:
            logger.error("[DB] update_trade_by_id failed: %s", e)
            return False


def get_trade(trade_id: str) -> Optional[Dict]:
    row = _execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
    return dict(row) if row else None


def list_trades(status: Optional[str] = None) -> List[Dict]:
    if status:
        rows = _execute("SELECT * FROM trades WHERE status = ? ORDER BY created_at DESC", (status,)).fetchall()
    else:
        rows = _execute("SELECT * FROM trades ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


def get_open_trades() -> List[Dict]:
    rows = _execute("SELECT * FROM trades WHERE status = 'OPEN' ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


def get_closed_trades() -> List[Dict]:
    rows = _execute("SELECT * FROM trades WHERE status != 'OPEN' ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


def delete_trade(trade_id: str) -> bool:
    with _write_lock:
        try:
            _execute("DELETE FROM trades WHERE id = ?", (trade_id,))
            _commit()
            return True
        except Exception as e:
            logger.error("[DB] delete_trade failed: %s", e)
            return False


def get_analytics() -> Dict[str, Any]:
    conn = _get_conn()

    total = conn.execute("SELECT count(*) FROM trades WHERE status != 'OPEN'").fetchone()[0]
    if total == 0:
        return {
            "total_trades": 0, "wins": 0, "losses": 0, "win_rate": 0,
            "avg_win": 0, "avg_loss": 0, "tp1_hits": 0, "tp2_hits": 0,
            "tp3_hits": 0, "sl_hits": 0, "avg_rr": 0, "total_pnl": 0,
            "open_trades": conn.execute("SELECT count(*) FROM trades WHERE status = 'OPEN'").fetchone()[0]
        }

    wins = conn.execute("SELECT count(*), coalesce(avg(pnl_pct),0) FROM trades WHERE status != 'OPEN' AND pnl_pct > 0").fetchone()
    losses = conn.execute("SELECT count(*), coalesce(abs(avg(pnl_pct)),0) FROM trades WHERE status != 'OPEN' AND pnl_pct <= 0").fetchone()

    tp1 = conn.execute("SELECT count(*) FROM trades WHERE status = 'TP1'").fetchone()[0]
    tp2 = conn.execute("SELECT count(*) FROM trades WHERE status = 'TP2'").fetchone()[0]
    tp3 = conn.execute("SELECT count(*) FROM trades WHERE status = 'TP3'").fetchone()[0]
    sl = conn.execute("SELECT count(*) FROM trades WHERE status = 'SL'").fetchone()[0]
    total_pnl = conn.execute("SELECT coalesce(sum(pnl_pct),0) FROM trades WHERE status != 'OPEN'").fetchone()[0]
    open_count = conn.execute("SELECT count(*) FROM trades WHERE status = 'OPEN'").fetchone()[0]

    win_count = wins[0]
    loss_count = losses[0]
    avg_win = wins[1] if wins[1] else 0
    avg_loss = losses[1] if losses[1] else 0

    return {
        "total_trades": total,
        "wins": win_count,
        "losses": loss_count,
        "win_rate": round(win_count / total * 100, 2) if total else 0,
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "tp1_hits": tp1,
        "tp2_hits": tp2,
        "tp3_hits": tp3,
        "sl_hits": sl,
        "avg_rr": round(avg_win / avg_loss, 2) if avg_loss > 0 else 0,
        "total_pnl": round(total_pnl, 2),
        "open_trades": open_count
    }


def migrate_from_json(json_path: str) -> int:
    import json as _json
    if not os.path.exists(json_path):
        return 0

    with open(json_path) as f:
        trades = _json.load(f)

    count = 0
    for t in trades:
        t.setdefault("quantity", None)
        t.setdefault("execution_mode", None)
        t.setdefault("order_id", None)
        t.setdefault("simulated", False)
        if insert_trade(t):
            count += 1

    if count > 0:
        logger.info("[DB] Migrated %d trades from %s", count, json_path)
    return count
