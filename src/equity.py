"""Equity agent and performance analytics for paper trading."""
from decimal import Decimal
from .storage import Storage
from .config import settings


def _d(x):
    return Decimal(str(x)) if x is not None else Decimal("0")


class EquityAgent:
    def __init__(self, storage: Storage):
        self.storage = storage

    def trades(self):
        cur = self.storage.conn.cursor()
        cur.execute("SELECT id,symbol,direction,entry_price,quantity,status,realized_pnl,fees,opened_at,closed_at FROM trades")
        rows = cur.fetchall()
        cols = ["id","symbol","direction","entry_price","quantity","status","realized_pnl","fees","opened_at","closed_at"]
        return [dict(zip(cols, r)) for r in rows]

    def analytics(self, current_prices=None):
        current_prices = current_prices or {}
        trades = self.trades()
        closed = [t for t in trades if t["status"] == "CLOSED"]
        open_trades = [t for t in trades if t["status"] == "OPEN"]

        starting = self.storage.get_setting("starting_equity")
        if starting is None:
            starting_eq = settings.simulated_starting_balance
        else:
            starting_eq = _d(starting)

        realized_pnl = sum((_d(t["realized_pnl"]) for t in closed), Decimal("0"))
        fees = sum((_d(t["fees"]) for t in closed), Decimal("0"))

        unrealized = Decimal("0")
        for t in open_trades:
            price = current_prices.get(t["symbol"])
            if price is None:
                continue
            qty = _d(t["quantity"])
            entry = _d(t["entry_price"])
            if t["direction"] == "LONG":
                unrealized += (_d(price) - entry) * qty
            else:
                unrealized += (entry - _d(price)) * qty

        current_equity = (starting_eq if starting_eq is not None else Decimal("0")) + realized_pnl + unrealized

        wins = [t for t in closed if _d(t["realized_pnl"]) > 0]
        losses = [t for t in closed if _d(t["realized_pnl"]) < 0]
        gross_profit = sum((_d(t["realized_pnl"]) for t in wins), Decimal("0"))
        gross_loss = sum((_d(t["realized_pnl"]) for t in losses), Decimal("0"))
        # gross loss as positive magnitude
        gross_loss_mag = abs(gross_loss)
        net_profit = realized_pnl
        win_rate = (len(wins) / len(closed) * 100) if closed else None
        profit_factor = (gross_profit / gross_loss_mag) if gross_loss_mag > 0 else (None if gross_profit == 0 else float("inf"))
        avg_win = (gross_profit / len(wins)) if wins else None
        avg_loss = (gross_loss_mag / len(losses)) if losses else None
        avg_ratio = (avg_win / avg_loss) if (avg_win is not None and avg_loss and avg_loss > 0) else None

        # consecutive wins/losses
        ordered = sorted(closed, key=lambda x: x.get("closed_at") or 0)
        max_consec_wins = 0
        max_consec_losses = 0
        cw = cl = 0
        for t in ordered:
            if _d(t["realized_pnl"]) > 0:
                cw += 1
                cl = 0
                max_consec_wins = max(max_consec_wins, cw)
            elif _d(t["realized_pnl"]) < 0:
                cl += 1
                cw = 0
                max_consec_losses = max(max_consec_losses, cl)
            else:
                cw = 0
                cl = 0

        # by symbol
        by_symbol = {}
        for t in closed:
            sym = t["symbol"]
            by_symbol.setdefault(sym, {"trades": 0, "pnl": Decimal("0"), "wins": 0})
            by_symbol[sym]["trades"] += 1
            by_symbol[sym]["pnl"] += _d(t["realized_pnl"])
            if _d(t["realized_pnl"]) > 0:
                by_symbol[sym]["wins"] += 1

        # by direction
        by_dir = {}
        for t in closed:
            d = t["direction"]
            by_dir.setdefault(d, {"trades": 0, "pnl": Decimal("0"), "wins": 0})
            by_dir[d]["trades"] += 1
            by_dir[d]["pnl"] += _d(t["realized_pnl"])
            if _d(t["realized_pnl"]) > 0:
                by_dir[d]["wins"] += 1

        # fees as % of gross profit
        fees_pct = (fees / gross_profit * 100) if gross_profit > 0 else None

        # drawdown from equity snapshots
        snaps = self.storage.get_equity_snapshots() if hasattr(self.storage, "get_equity_snapshots") else []
        # if method not exists, fetch manually
        if not snaps:
            cur = self.storage.conn.cursor()
            cur.execute("SELECT ts,equity FROM equity_snapshots ORDER BY ts ASC")
            snaps = [{"ts": r[0], "equity": r[1]} for r in cur.fetchall()]

        peak = None
        max_dd = Decimal("0")
        max_dd_pct = Decimal("0")
        for s in snaps:
            eq = _d(s["equity"])
            if peak is None or eq > peak:
                peak = eq
            if peak and peak > 0:
                dd = peak - eq
                if dd > max_dd:
                    max_dd = dd
                    max_dd_pct = (dd / peak * 100)

        # if no snapshots, compute peak from current equity
        if peak is None:
            peak = current_equity
            max_dd = Decimal("0")
            max_dd_pct = Decimal("0")

        return {
            "starting_equity": (str(starting_eq) if starting_eq is not None else None),
            "current_equity": str(current_equity),
            "realized_pnl": str(realized_pnl),
            "unrealized_pnl": str(unrealized),
            "fees": str(fees),
            "net_pnl": str(realized_pnl + unrealized),
            "total_trades": len(closed),
            "open_trades": len(open_trades),
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "win_rate": (round(win_rate, 2) if win_rate is not None else None),
            "gross_profit": str(gross_profit),
            "gross_loss": str(gross_loss_mag),
            "net_profit": str(net_profit),
            "profit_factor": (str(profit_factor) if profit_factor is not None and profit_factor != float("inf") else ("inf" if profit_factor == float("inf") else None)),
            "average_win": (str(avg_win) if avg_win is not None else None),
            "average_loss": (str(avg_loss) if avg_loss is not None else None),
            "average_win_loss_ratio": (str(avg_ratio) if avg_ratio is not None else None),
            "max_drawdown": str(max_dd),
            "max_drawdown_percent": str(max_dd_pct),
            "peak_equity": str(peak),
            "consecutive_wins_max": max_consec_wins,
            "consecutive_losses_max": max_consec_losses,
            "fees_percent_of_gross_profit": (str(fees_pct) if fees_pct is not None else None),
            "by_symbol": {k: {"trades": v["trades"], "pnl": str(v["pnl"]), "wins": v["wins"]} for k, v in by_symbol.items()},
            "by_direction": {k: {"trades": v["trades"], "pnl": str(v["pnl"]), "wins": v["wins"]} for k, v in by_dir.items()},
            "unavailable": {
                "win_rate": win_rate is None,
                "profit_factor": profit_factor is None,
                "average_win": avg_win is None,
                "average_loss": avg_loss is None,
            }
        }

    def snapshot(self, current_prices=None):
        current_prices = current_prices or {}
        a = self.analytics(current_prices)
        self.storage.add_equity_snapshot(
            equity=a["current_equity"],
            balance=a["current_equity"],
            realized_pnl=a["realized_pnl"],
            unrealized_pnl=a["unrealized_pnl"],
        )
        return a

    def history(self, limit=200):
        cur = self.storage.conn.cursor()
        cur.execute("SELECT id,ts,equity,balance,realized_pnl,unrealized_pnl FROM equity_snapshots ORDER BY id DESC LIMIT ?", (limit,))
        rows = cur.fetchall()
        cols = ["id","ts","equity","balance","realized_pnl","unrealized_pnl"]
        return [dict(zip(cols, r)) for r in rows]

    def drawdown_series(self, limit=500):
        hist = list(reversed(self.history(limit=limit)))
        peak = None
        series = []
        for h in hist:
            eq = _d(h["equity"])
            if peak is None or eq > peak:
                peak = eq
            dd = (peak - eq) if peak else Decimal("0")
            dd_pct = (dd / peak * 100) if (peak and peak > 0) else Decimal("0")
            series.append({"ts": h["ts"], "equity": str(eq), "peak": str(peak), "drawdown": str(dd), "drawdown_percent": str(dd_pct)})
        return series