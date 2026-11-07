"""SQLite persistence for trades, signals, kill-switch state."""
import os
import sqlite3
import time
from pathlib import Path
from decimal import Decimal
from .config import settings


def _db_path() -> str:
    url = os.getenv("DATABASE_URL") or settings.database_url
    if url.startswith("sqlite:///"):
        return url.replace("sqlite:///", "")
    return "data/bot.db"


class Storage:
    def __init__(self, path: str | None = None):
        self.path = path or _db_path()
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, check_same_thread=False, timeout=30)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=30000")
        self._init_schema()
        self._migrate()

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
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL,
            agent TEXT,
            symbol TEXT,
            event_type TEXT,
            status TEXT,
            reason TEXT,
            trade_id TEXT,
            severity TEXT,
            message TEXT,
            metadata TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);

        CREATE TABLE IF NOT EXISTS agent_status (
            name TEXT PRIMARY KEY,
            status TEXT,
            last_activity REAL,
            last_success REAL,
            error_message TEXT,
            tasks_completed INTEGER DEFAULT 0,
            current_activity TEXT
        );
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT,
            side TEXT,
            type TEXT,
            quantity TEXT,
            price TEXT,
            status TEXT,
            order_id TEXT,
            created_at REAL
        );
        CREATE TABLE IF NOT EXISTS positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT,
            direction TEXT,
            quantity TEXT,
            entry_price TEXT,
            status TEXT,
            updated_at REAL
        );
        CREATE TABLE IF NOT EXISTS equity_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL,
            equity TEXT,
            balance TEXT,
            realized_pnl TEXT,
            unrealized_pnl TEXT
        );
        CREATE TABLE IF NOT EXISTS admin_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL,
            action TEXT,
            actor TEXT,
            details TEXT
        );
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            must_change_password INTEGER DEFAULT 0,
            is_admin INTEGER DEFAULT 1,
            created_at REAL
        );
        CREATE TABLE IF NOT EXISTS sessions (
            token_hash TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            created_at REAL,
            expires_at REAL,
            revoked INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS scanner_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL,
            symbol TEXT,
            direction TEXT,
            entry_price TEXT,
            stop_loss TEXT,
            take_profit TEXT,
            score REAL,
            indicators TEXT,
            explanation TEXT,
            candle_time INTEGER
        );
        CREATE TABLE IF NOT EXISTS risk_assessments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL,
            symbol TEXT,
            rating TEXT,
            reasons TEXT,
            warnings TEXT,
            metrics TEXT
        );
        CREATE TABLE IF NOT EXISTS signal_diagnostics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL,
            symbol TEXT,
            regime TEXT,
            regime_detail TEXT,
            long_score REAL,
            long_decision TEXT,
            long_reason TEXT,
            long_checks TEXT,
            short_score REAL,
            short_decision TEXT,
            short_reason TEXT,
            short_checks TEXT,
            final_decision TEXT,
            rejection_reason TEXT,
            signal_id TEXT,
            strategy TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_diag_ts ON signal_diagnostics(ts);
        CREATE INDEX IF NOT EXISTS idx_diag_symbol ON signal_diagnostics(symbol);
        CREATE TABLE IF NOT EXISTS scan_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL,
            total_scans INTEGER,
            qualified INTEGER,
            watchlist INTEGER,
            errors INTEGER,
            avg_long_score REAL,
            avg_short_score REAL
        );
        CREATE TABLE IF NOT EXISTS market_candles (
            symbol TEXT NOT NULL,
            interval TEXT NOT NULL,
            updated_at REAL,
            candles TEXT,
            PRIMARY KEY (symbol, interval)
        );
        CREATE TABLE IF NOT EXISTS market_universe (
            symbol TEXT PRIMARY KEY,
            quote_volume TEXT,
            updated_at REAL
        );
        CREATE TABLE IF NOT EXISTS market_meta (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        INSERT OR IGNORE INTO agent_status (name,status) VALUES ('ADMIN','IDLE');
        """)
        self.conn.commit()

    def _migrate(self):
        cur = self.conn.cursor()
        cols = {r[1] for r in cur.execute("PRAGMA table_info(events)").fetchall()}
        for col, ctype in (("severity", "TEXT"), ("message", "TEXT"), ("metadata", "TEXT")):
            if col not in cols:
                try:
                    cur.execute(f"ALTER TABLE events ADD COLUMN {col} {ctype}")
                except Exception:
                    pass
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

    def save_signal_diagnostic(self, diag):
        import json
        d = diag.to_dict() if hasattr(diag, "to_dict") else dict(diag)
        le = d.get("long_eval") or {}
        se = d.get("short_eval") or {}
        rd = d.get("regime_detail") or {}
        strategy = le.get("strategy") if d.get("final_decision") == "SIGNAL" and le.get("decision") == "ACCEPTED" else (
            se.get("strategy") if d.get("final_decision") == "SIGNAL" else le.get("strategy") or se.get("strategy") or "")
        cur = self.conn.cursor()
        cur.execute(
            """INSERT INTO signal_diagnostics
               (ts,symbol,regime,regime_detail,long_score,long_decision,long_reason,long_checks,
                short_score,short_decision,short_reason,short_checks,final_decision,rejection_reason,signal_id,strategy)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (d.get("timestamp", time.time()), d.get("symbol", ""), d.get("regime", ""),
             json.dumps(rd), le.get("score", 0.0), le.get("decision", ""), le.get("reason", ""),
             json.dumps(le.get("checks", {})), se.get("score", 0.0), se.get("decision", ""), se.get("reason", ""),
             json.dumps(se.get("checks", {})), d.get("final_decision", ""), d.get("rejection_reason", ""),
             d.get("signal_id", ""), strategy),
        )
        self.conn.commit()

    def recent_diagnostics(self, limit: int = 50, symbol: str | None = None, signals_only: bool = False) -> list[dict]:
        cur = self.conn.cursor()
        q = "SELECT * FROM signal_diagnostics"
        conds, params = [], []
        if symbol:
            conds.append("symbol=?")
            params.append(symbol)
        if signals_only:
            conds.append("final_decision='SIGNAL'")
        if conds:
            q += " WHERE " + " AND ".join(conds)
        q += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        cols = [c[1] for c in cur.execute("PRAGMA table_info(signal_diagnostics)").fetchall()]
        return [dict(zip(cols, r)) for r in cur.execute(q, params).fetchall()]

    def save_scan_stats(self, stats: dict):
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO scan_stats (ts,total_scans,qualified,watchlist,errors,avg_long_score,avg_short_score) VALUES (?,?,?,?,?,?,?)",
            (stats.get("ts", time.time()), stats.get("total_scans", 0), stats.get("qualified", 0),
             stats.get("watchlist", 0), stats.get("errors", 0), stats.get("avg_long_score", 0.0), stats.get("avg_short_score", 0.0)),
        )
        self.conn.commit()

    def diagnostics_summary(self) -> dict:
        cur = self.conn.cursor()
        total = cur.execute("SELECT COUNT(*) FROM signal_diagnostics").fetchone()[0]
        signals = cur.execute("SELECT COUNT(*) FROM signal_diagnostics WHERE final_decision='SIGNAL'").fetchone()[0]
        by_symbol = cur.execute(
            "SELECT symbol, COUNT(*), SUM(CASE WHEN final_decision='SIGNAL' THEN 1 ELSE 0 END) FROM signal_diagnostics GROUP BY symbol"
        ).fetchall()
        by_strategy = cur.execute(
            "SELECT strategy, COUNT(*) FROM signal_diagnostics WHERE final_decision='SIGNAL' AND strategy!='' GROUP BY strategy"
        ).fetchall()
        by_regime = cur.execute(
            "SELECT regime, COUNT(*) FROM signal_diagnostics GROUP BY regime"
        ).fetchall()
        top_reasons = cur.execute(
            "SELECT rejection_reason, COUNT(*) AS c FROM signal_diagnostics WHERE final_decision='NO_TRADE' AND rejection_reason!='' GROUP BY rejection_reason ORDER BY c DESC LIMIT 10"
        ).fetchall()
        avgs = cur.execute(
            "SELECT AVG(long_score), AVG(short_score) FROM signal_diagnostics"
        ).fetchone()
        return {
            "total_scans": total,
            "signals": signals,
            "rejected": total - signals,
            "by_symbol": [{"symbol": r[0], "scans": r[1], "signals": r[2] or 0} for r in by_symbol],
            "by_strategy": [{"strategy": r[0], "signals": r[1]} for r in by_strategy],
            "by_regime": [{"regime": r[0], "count": r[1]} for r in by_regime],
            "top_rejection_reasons": [{"reason": r[0], "count": r[1]} for r in top_reasons],
            "avg_long_score": round(avgs[0] or 0.0, 1),
            "avg_short_score": round(avgs[1] or 0.0, 1),
        }

    def prune_diagnostics(self, keep: int = 10000):
        cur = self.conn.cursor()
        cur.execute("DELETE FROM signal_diagnostics WHERE id NOT IN (SELECT id FROM signal_diagnostics ORDER BY id DESC LIMIT ?)", (keep,))
        cur.execute("DELETE FROM scan_stats WHERE id NOT IN (SELECT id FROM scan_stats ORDER BY id DESC LIMIT ?)", (keep,))
        self.conn.commit()

    def log_event(self, agent: str, symbol: str = "", event_type: str = "", status: str = "", reason: str = "", trade_id: str = "",
                  severity: str = "INFO", message: str = "", metadata=None):
        import json as _j
        cur = self.conn.cursor()
        cur.execute("""INSERT INTO events (ts, agent, symbol, event_type, status, reason, trade_id, severity, message, metadata)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (time.time(), agent, symbol, event_type, status, reason, trade_id, severity, message or reason,
                     (_j.dumps(metadata) if metadata is not None else None)))
        self.conn.commit()

    def recent_events(self, limit: int = 100, agent: str = "", severity: str = "", event_type: str = "",
                      symbol: str = "", offset: int = 0, start_ts=None, end_ts=None) -> list[dict]:
        cur = self.conn.cursor()
        where = []
        params = []
        if agent:
            where.append("agent=?")
            params.append(agent)
        if severity:
            where.append("severity=?")
            params.append(severity)
        if event_type:
            where.append("event_type=?")
            params.append(event_type)
        if symbol:
            where.append("symbol=?")
            params.append(symbol)
        if start_ts is not None:
            where.append("ts>=?")
            params.append(start_ts)
        if end_ts is not None:
            where.append("ts<=?")
            params.append(end_ts)
        sql = "SELECT id,ts,agent,symbol,event_type,status,reason,trade_id,severity,message,metadata FROM events"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        cur.execute(sql, params)
        rows = cur.fetchall()
        cols = ["id", "ts", "agent", "symbol", "event_type", "status", "reason", "trade_id", "severity", "message", "metadata"]
        import json as _j
        out = []
        for r in rows:
            d = dict(zip(cols, r))
            if d.get("metadata"):
                try:
                    d["metadata"] = _j.loads(d["metadata"])
                except Exception:
                    pass
            out.append(d)
        return out

    def count_events(self, agent="", severity="", event_type="", symbol="") -> int:
        cur = self.conn.cursor()
        where = []
        params = []
        if agent:
            where.append("agent=?"); params.append(agent)
        if severity:
            where.append("severity=?"); params.append(severity)
        if event_type:
            where.append("event_type=?"); params.append(event_type)
        if symbol:
            where.append("symbol=?"); params.append(symbol)
        sql = "SELECT COUNT(*) FROM events"
        if where:
            sql += " WHERE " + " AND ".join(where)
        cur.execute(sql, params)
        return cur.fetchone()[0]

    def prune_logs(self, retention_days: int = 30, keep_important: bool = True):
        import time as _t
        cutoff = _t.time() - retention_days * 86400
        cur = self.conn.cursor()
        if keep_important:
            cur.execute("DELETE FROM events WHERE ts < ? AND event_type NOT IN ('trade','execution','paper_open','paper_close')", (cutoff,))
        else:
            cur.execute("DELETE FROM events WHERE ts < ?", (cutoff,))
        self.conn.commit()
        return cur.rowcount

    def equity_summary(self) -> dict:
        cur = self.conn.cursor()
        cur.execute("SELECT COALESCE(SUM(CAST(realized_pnl AS REAL)),0), COALESCE(SUM(CAST(fees AS REAL)),0), COUNT(*) FROM trades")
        rp, fees, total = cur.fetchone()
        cur.execute("SELECT COUNT(*) FROM trades WHERE status='OPEN'")
        open_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM trades WHERE status='CLOSED' AND CAST(realized_pnl AS REAL)>0")
        wins = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM trades WHERE status='CLOSED'")
        closed = cur.fetchone()[0]
        return {"realized_pnl": rp or 0, "fees": fees or 0, "total_trades": total or 0,
                "open_positions": open_count or 0, "wins": wins or 0, "closed": closed or 0,
                "win_rate": (wins / closed * 100) if closed else 0}

    # Agent status
    def upsert_agent_status(self, name, status, current_activity="", error_message="", tasks_completed=None, last_success=False):
        cur = self.conn.cursor()
        cur.execute("SELECT tasks_completed FROM agent_status WHERE name=?", (name,))
        row = cur.fetchone()
        tc = row[0] if row else 0
        if tasks_completed is not None:
            tc = tasks_completed
        if last_success:
            cur.execute("""INSERT INTO agent_status (name,status,last_activity,last_success,error_message,tasks_completed,current_activity)
                           VALUES (?,?,?,?,?,?,?)
                           ON CONFLICT(name) DO UPDATE SET status=?,last_activity=?,last_success=?,error_message=?,tasks_completed=?,current_activity=?""",
                        (name, status, time.time(), time.time(), error_message, tc, current_activity,
                         status, time.time(), time.time(), error_message, tc, current_activity))
        else:
            cur.execute("""INSERT INTO agent_status (name,status,last_activity,last_success,error_message,tasks_completed,current_activity)
                           VALUES (?,?,?,?,?,?,?)
                           ON CONFLICT(name) DO UPDATE SET status=?,last_activity=?,error_message=?,tasks_completed=?,current_activity=?""",
                        (name, status, time.time(), None, error_message, tc, current_activity,
                         status, time.time(), error_message, tc, current_activity))
        self.conn.commit()

    def get_agent_statuses(self) -> list[dict]:
        cur = self.conn.cursor()
        cur.execute("SELECT name,status,last_activity,last_success,error_message,tasks_completed,current_activity FROM agent_status")
        rows = cur.fetchall()
        cols = ["name","status","last_activity","last_success","error_message","tasks_completed","current_activity"]
        return [dict(zip(cols, r)) for r in rows]

    # Settings KV
    def get_setting(self, key, default=None):
        cur = self.conn.cursor()
        cur.execute("SELECT value FROM settings WHERE key=?", (key,))
        r = cur.fetchone()
        return r[0] if r else default

    def set_setting(self, key, value):
        cur = self.conn.cursor()
        cur.execute("INSERT INTO settings (key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=?", (key, value, value))
        self.conn.commit()

    # Admin actions
    def log_admin_action(self, action, actor="admin", details=""):
        cur = self.conn.cursor()
        cur.execute("INSERT INTO admin_actions (ts,action,actor,details) VALUES (?,?,?,?)", (time.time(), action, actor, details))
        self.conn.commit()

    def recent_admin_actions(self, limit=50):
        cur = self.conn.cursor()
        cur.execute("SELECT id,ts,action,actor,details FROM admin_actions ORDER BY id DESC LIMIT ?", (limit,))
        rows = cur.fetchall()
        cols = ["id","ts","action","actor","details"]
        return [dict(zip(cols, r)) for r in rows]

    # Equity snapshots
    def add_equity_snapshot(self, equity, balance, realized_pnl, unrealized_pnl=0):
        cur = self.conn.cursor()
        cur.execute("INSERT INTO equity_snapshots (ts,equity,balance,realized_pnl,unrealized_pnl) VALUES (?,?,?,?,?)",
                    (time.time(), str(equity), str(balance), str(realized_pnl), str(unrealized_pnl)))
        self.conn.commit()

    # Orders
    def add_order(self, symbol, side, otype, quantity, price=None, status="NEW", order_id=None):
        cur = self.conn.cursor()
        cur.execute("INSERT INTO orders (symbol,side,type,quantity,price,status,order_id,created_at) VALUES (?,?,?,?,?,?,?,?)",
                    (symbol, side, otype, str(quantity), (str(price) if price is not None else None), status, (str(order_id) if order_id is not None else None), time.time()))
        self.conn.commit()
        return cur.lastrowid

    def recent_orders(self, limit=50):
        cur = self.conn.cursor()
        cur.execute("SELECT id,symbol,side,type,quantity,price,status,order_id,created_at FROM orders ORDER BY id DESC LIMIT ?", (limit,))
        rows = cur.fetchall()
        cols = ["id","symbol","side","type","quantity","price","status","order_id","created_at"]
        return [dict(zip(cols, r)) for r in rows]

    def save_scanner_result(self, symbol, direction, entry_price, stop_loss, take_profit, score, indicators, explanation, candle_time):
        import json
        cur = self.conn.cursor()
        cur.execute("""INSERT INTO scanner_results (ts,symbol,direction,entry_price,stop_loss,take_profit,score,indicators,explanation,candle_time)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (time.time(), symbol, direction, str(entry_price), str(stop_loss), str(take_profit), float(score), json.dumps(indicators), explanation, int(candle_time)))
        self.conn.commit()
        return cur.lastrowid

    def recent_scanner_results(self, limit=50, symbol=""):
        import json
        cur = self.conn.cursor()
        if symbol:
            cur.execute("SELECT id,ts,symbol,direction,entry_price,stop_loss,take_profit,score,indicators,explanation,candle_time FROM scanner_results WHERE symbol=? ORDER BY id DESC LIMIT ?", (symbol, limit))
        else:
            cur.execute("SELECT id,ts,symbol,direction,entry_price,stop_loss,take_profit,score,indicators,explanation,candle_time FROM scanner_results ORDER BY id DESC LIMIT ?", (limit,))
        rows = cur.fetchall()
        cols = ["id","ts","symbol","direction","entry_price","stop_loss","take_profit","score","indicators","explanation","candle_time"]
        out = []
        for r in rows:
            d = dict(zip(cols, r))
            try:
                d["indicators"] = json.loads(d["indicators"]) if d["indicators"] else {}
            except Exception:
                pass
            out.append(d)
        return out

    def save_risk_assessment(self, symbol, rating, reasons, warnings, metrics):
        import json
        cur = self.conn.cursor()
        cur.execute("INSERT INTO risk_assessments (ts,symbol,rating,reasons,warnings,metrics) VALUES (?,?,?,?,?,?)",
                    (time.time(), symbol, rating, json.dumps(reasons), json.dumps(warnings), json.dumps(metrics)))
        self.conn.commit()
        return cur.lastrowid

    def latest_risk_assessment(self, symbol):
        import json
        cur = self.conn.cursor()
        cur.execute("SELECT id,ts,symbol,rating,reasons,warnings,metrics FROM risk_assessments WHERE symbol=? ORDER BY id DESC LIMIT 1", (symbol,))
        r = cur.fetchone()
        if not r:
            return None
        cols = ["id","ts","symbol","rating","reasons","warnings","metrics"]
        d = dict(zip(cols, r))
        for k in ("reasons","warnings","metrics"):
            try:
                d[k] = json.loads(d[k])
            except Exception:
                pass
        return d

    # Market data cache (all USDT-M perpetuals)
    def save_market_candles(self, symbol, interval, candles, updated_at=None):
        self.save_market_candles_bulk([(symbol, interval, candles)], updated_at=updated_at)

    def save_market_candles_bulk(self, items, updated_at=None):
        import json
        ts = time.time() if updated_at is None else updated_at
        rows = [(str(symbol), str(interval), ts, json.dumps(candles, separators=(",", ":")))
                for symbol, interval, candles in items]
        if not rows:
            return
        with self.conn:
            self.conn.executemany(
                """INSERT INTO market_candles (symbol,interval,updated_at,candles) VALUES (?,?,?,?)
                   ON CONFLICT(symbol,interval) DO UPDATE SET updated_at=excluded.updated_at, candles=excluded.candles""",
                rows)

    def get_market_candles(self, symbol, interval):
        import json
        cur = self.conn.cursor()
        cur.execute("SELECT candles, updated_at FROM market_candles WHERE symbol=? AND interval=?", (symbol, interval))
        r = cur.fetchone()
        if not r:
            return [], 0.0
        try:
            return json.loads(r[0]), float(r[1] or 0.0)
        except Exception:
            return [], float(r[1] or 0.0)

    def save_market_universe(self, symbols):
        now = time.time()
        rows = []
        for item in symbols:
            if isinstance(item, (tuple, list)):
                sym, qv = item[0], item[1] if len(item) > 1 else ""
            else:
                sym, qv = item, ""
            rows.append((str(sym), str(qv), now))
        with self.conn:
            self.conn.execute("DELETE FROM market_universe")
            self.conn.executemany(
                "INSERT OR REPLACE INTO market_universe (symbol,quote_volume,updated_at) VALUES (?,?,?)", rows)

    def get_market_universe(self):
        cur = self.conn.cursor()
        cur.execute("SELECT symbol FROM market_universe ORDER BY symbol")
        return [r[0] for r in cur.fetchall()]

    def set_market_meta(self, key, value):
        with self.conn:
            self.conn.execute("INSERT OR REPLACE INTO market_meta (key,value) VALUES (?,?)", (str(key), str(value)))

    def get_market_meta(self, key, default=None):
        cur = self.conn.cursor()
        cur.execute("SELECT value FROM market_meta WHERE key=?", (str(key),))
        r = cur.fetchone()
        return r[0] if r else default

    def market_data_summary(self):
        cur = self.conn.cursor()
        symbols = cur.execute("SELECT COUNT(*) FROM market_universe").fetchone()[0]
        cached = cur.execute("SELECT COUNT(*) FROM market_candles").fetchone()[0]
        row = cur.execute("SELECT MAX(updated_at) FROM market_candles").fetchone()
        return {
            "universe_symbols": symbols,
            "cached_series": cached,
            "last_candle_update": row[0] if row else None,
            "last_refresh": self.get_market_meta("last_refresh"),
            "last_refresh_status": self.get_market_meta("last_refresh_status", ""),
            "last_refresh_count": self.get_market_meta("last_refresh_count", "0"),
        }

    # Users
    def create_user(self, username, password_hash, salt, must_change_password=False):
        cur = self.conn.cursor()
        cur.execute("INSERT OR REPLACE INTO users (username,password_hash,salt,must_change_password,is_admin,created_at) VALUES (?,?,?,?,?,?)",
                    (username, password_hash, salt, 1 if must_change_password else 0, 1, time.time()))
        self.conn.commit()

    def get_user(self, username):
        cur = self.conn.cursor()
        cur.execute("SELECT username,password_hash,salt,must_change_password,is_admin,created_at FROM users WHERE username=?", (username,))
        r = cur.fetchone()
        if not r:
            return None
        cols = ["username","password_hash","salt","must_change_password","is_admin","created_at"]
        return dict(zip(cols, r))

    def has_admin(self):
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM users")
        return cur.fetchone()[0] > 0

    # Sessions
    def create_session(self, token_hash, username, expires_at):
        cur = self.conn.cursor()
        cur.execute("INSERT INTO sessions (token_hash,username,created_at,expires_at,revoked) VALUES (?,?,?,?,0)",
                    (token_hash, username, time.time(), expires_at))
        self.conn.commit()

    def get_session(self, token_hash):
        cur = self.conn.cursor()
        cur.execute("SELECT token_hash,username,created_at,expires_at,revoked FROM sessions WHERE token_hash=?", (token_hash,))
        r = cur.fetchone()
        if not r:
            return None
        cols = ["token_hash","username","created_at","expires_at","revoked"]
        return dict(zip(cols, r))

    def revoke_session(self, token_hash):
        cur = self.conn.cursor()
        cur.execute("UPDATE sessions SET revoked=1 WHERE token_hash=?", (token_hash,))
        self.conn.commit()

    def revoke_user_sessions(self, username):
        cur = self.conn.cursor()
        cur.execute("UPDATE sessions SET revoked=1 WHERE username=?", (username,))
        self.conn.commit()

    def get_equity_snapshots(self, limit=500):
        cur = self.conn.cursor()
        cur.execute("SELECT id,ts,equity,balance,realized_pnl,unrealized_pnl FROM equity_snapshots ORDER BY id DESC LIMIT ?", (limit,))
        rows = cur.fetchall()
        cols = ["id","ts","equity","balance","realized_pnl","unrealized_pnl"]
        return [dict(zip(cols, r)) for r in rows]

    def close(self):
        self.conn.close()
