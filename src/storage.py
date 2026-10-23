"""SQLite persistence for trades, signals, kill-switch state."""
import sqlite3
import json
import time
from pathlib import Path
from decimal import Decimal
from .config import settings


def _db_path() -> str:
    url = settings.database_url
    if url.startswith("sqlite:///"):
        return url.replace("sqlite:///", "")
    return "data/bot.db"


class Storage:
    def __init__(self, path: str | None = None):
        self.path = path or _db_path()
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self._init_schema()

    def _init_schema(self):
        cur = self.conn.cursor()
        cur.executescript("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT, direction TEXT, entry_price TEXT, stop_loss TEXT,
            take_profit TEXT, quantity TEXT, status TEXT, entry_order_id TEXT,
            stop_order_id TEXT, opened_at REAL, closed_at REAL, realized_pnl TEXT,
            fees TEXT, funding TEXT
        );
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT, direction TEXT, timestamp INTEGER, entry_price TEXT,
            stop_loss TEXT, take_profit TEXT, accepted INTEGER, rejection_reason TEXT
        );
        CREATE TABLE IF NOT EXISTS kill_switch (
            id INTEGER PRIMARY KEY CHECK (id=1),
            halted INTEGER NOT NULL,
            reason TEXT,
            halted_at REAL
        );
        INSERT OR IGNORE INTO kill_switch (id, halted) VALUES (1, 0);
        CREATE TABLE IF NOT EXISTS daily_loss (
            day TEXT PRIMARY KEY,
            realized_loss TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS worker_heartbeat (
            id INTEGER PRIMARY KEY CHECK (id=1),
            last_beat REAL,
            status TEXT
        );
        INSERT OR IGNORE INTO worker_heartbeat (id) VALUES (1);
        CREATE TABLE IF NOT EXISTS reconciliation_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL,
            result TEXT
        );
        CREATE TABLE IF NOT EXISTS seen_signals (
            signal_id TEXT PRIMARY KEY
        );
        """)
        self.conn.commit()

    def save_signal(self, sig, accepted: bool, reason: str = ""):
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO signals (symbol,direction,timestamp,entry_price,stop_loss,take_profit,accepted,rejection_reason) VALUES (?,?,?,?,?,?,?,?)",
            (getattr(sig, "symbol", ""), getattr(sig, "direction", ""), getattr(sig, "timestamp", 0), str(getattr(sig, "entry_price", "")), str(getattr(sig, "stop_loss", "")), str(getattr(sig, "take_profit", "")), 1 if accepted else 0, reason),
        )
        self.conn.commit()

    def open_trade(self, trade: dict) -> int:
        cur = self.conn.cursor()
        cur.execute(
            """INSERT INTO trades (symbol,direction,entry_price,stop_loss,take_profit,quantity,status,entry_order_id,stop_order_id,opened_at,realized_pnl,fees,funding)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (trade["symbol"], trade["direction"], str(trade["entry_price"]), str(trade["stop_loss"]), str(trade["take_profit"]),
             str(trade["quantity"]), "OPEN", trade.get("entry_order_id"), trade.get("stop_order_id"), time.time(),
             "0", "0", "0"),
        )
        self.conn.commit()
        return cur.lastrowid

    def close_trade(self, trade_id: int, realized_pnl: str, fees: str):
        cur = self.conn.cursor()
        cur.execute("UPDATE trades SET status='CLOSED', closed_at=?, realized_pnl=?, fees=? WHERE id=?",
                    (time.time(), realized_pnl, fees, trade_id))
        self.conn.commit()

    def open_positions(self) -> list[dict]:
        cur = self.conn.cursor()
        cur.execute("SELECT id,symbol,direction,quantity,entry_price,stop_loss,take_profit,entry_order_id,stop_order_id FROM trades WHERE status='OPEN'")
        rows = cur.fetchall()
        return [{"id": r[0], "symbol": r[1], "direction": r[2], "quantity": r[3], "entry_price": r[4],
                "stop_loss": r[5], "take_profit": r[6], "entry_order_id": r[7], "stop_order_id": r[8]} for r in rows]

    def is_halted(self) -> tuple[bool, str]:
        cur = self.conn.cursor()
        cur.execute("SELECT halted, reason FROM kill_switch WHERE id=1")
        r = cur.fetchone()
        return bool(r[0]), (r[1] or "")

    def set_halted(self, halted: bool, reason: str = ""):
        cur = self.conn.cursor()
        cur.execute("UPDATE kill_switch SET halted=?, reason=?, halted_at=? WHERE id=1",
                    (1 if halted else 0, reason, time.time() if halted else None))
        self.conn.commit()

    def daily_loss(self, day: str) -> Decimal:
        from decimal import Decimal
        cur = self.conn.cursor()
        cur.execute("SELECT realized_loss FROM daily_loss WHERE day=?", (day,))
        r = cur.fetchone()
        return Decimal(r[0]) if r else Decimal("0")

    def add_daily_loss(self, day: str, amount: Decimal):
        cur = self.conn.cursor()
        cur.execute("INSERT INTO daily_loss (day, realized_loss) VALUES (?, ?) ON CONFLICT(day) DO UPDATE SET realized_loss=realized_loss+?",
                    (day, str(amount), str(amount)))
        self.conn.commit()

    def mark_signal_seen(self, signal_id: str) -> bool:
        try:
            self.conn.execute("INSERT INTO seen_signals (signal_id) VALUES (?)", (signal_id,))
            self.conn.commit()
            return True
        except Exception:
            return False

    def is_signal_seen(self, signal_id: str) -> bool:
        cur = self.conn.cursor()
        cur.execute("SELECT 1 FROM seen_signals WHERE signal_id=?", (signal_id,))
        return cur.fetchone() is not None

    def update_heartbeat(self, status: str = "ok"):
        import time
        cur = self.conn.cursor()
        cur.execute("UPDATE worker_heartbeat SET last_beat=?, status=? WHERE id=1", (time.time(), status))
        self.conn.commit()

    def get_heartbeat(self):
        cur = self.conn.cursor()
        cur.execute("SELECT last_beat, status FROM worker_heartbeat WHERE id=1")
        r = cur.fetchone()
        return {"last_beat": r[0], "status": r[1]} if r else {}

    def log_reconciliation(self, result: str):
        import time
        cur = self.conn.cursor()
        cur.execute("INSERT INTO reconciliation_log (ts, result) VALUES (?, ?)", (time.time(), result))
        self.conn.commit()

    def close(self):
        self.conn.close()
