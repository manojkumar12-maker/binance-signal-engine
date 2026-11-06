"""Paper trading engine (simulated execution)."""
from decimal import Decimal
from .storage import Storage
from .config import settings
from .risk_engine import fee_estimate


class PaperTrader:
    def __init__(self, storage: Storage):
        self.storage = storage

    def _current_price(self, client, symbol):
        try:
            return client.ticker_price(symbol)
        except Exception:
            return None

    def open_position(self, client, trade_proposal, size_decision, signal) -> dict:
        # prevent duplicate
        if self.storage.open_positions():
            return {"ok": False, "reason": "position already open"}
        symbol = trade_proposal["symbol"] if isinstance(trade_proposal, dict) else trade_proposal.symbol
        direction = trade_proposal["direction"] if isinstance(trade_proposal, dict) else trade_proposal.direction
        entry = Decimal(str(trade_proposal.get("entry_price") if isinstance(trade_proposal, dict) else trade_proposal.entry_price))
        # use market price if available
        mp = self._current_price(client, symbol)
        if mp is not None:
            entry = mp
        # slippage
        slip = entry * settings.estimated_slippage
        if direction == "LONG":
            entry = entry + slip
        else:
            entry = entry - slip

        qty = size_decision.quantity if hasattr(size_decision, "quantity") else Decimal(str(size_decision["quantity"]))
        sl = Decimal(str(trade_proposal.get("stop_loss") if isinstance(trade_proposal, dict) else trade_proposal.stop_loss))
        tp = Decimal(str(trade_proposal.get("take_profit") if isinstance(trade_proposal, dict) else trade_proposal.take_profit))

        trade = {
            "symbol": symbol,
            "direction": direction,
            "entry_price": entry,
            "stop_loss": sl,
            "take_profit": tp,
            "quantity": qty,
            "entry_order_id": "PAPER",
            "stop_order_id": "PAPER",
        }
        tid = self.storage.open_trade(trade)
        self.storage.add_order(symbol, "BUY" if direction == "LONG" else "SELL", "MARKET", qty, entry, "FILLED", "PAPER")
        self.storage.log_event("EXECUTER", symbol, "paper_open", "executed", f"trade_id={tid} qty={qty} entry={entry}")
        return {"ok": True, "trade_id": tid, "entry_price": str(entry), "quantity": str(qty)}

    def close_position(self, trade_id, price, reason="manual") -> dict:
        # find trade
        positions = self.storage.open_positions()
        trade = None
        for p in positions:
            if p["id"] == trade_id:
                trade = p
                break
        if trade is None:
            return {"ok": False, "reason": "trade not found"}
        symbol = trade["symbol"]
        direction = trade["direction"]
        qty = Decimal(str(trade["quantity"]))
        entry = Decimal(str(trade["entry_price"]))
        sl = Decimal(str(trade["stop_loss"]))
        tp = Decimal(str(trade["take_profit"]))
        exit_price = Decimal(str(price))
        # slippage
        slip = exit_price * settings.estimated_slippage
        if direction == "LONG":
            exit_price = exit_price - slip
        else:
            exit_price = exit_price + slip

        if direction == "LONG":
            pnl = (exit_price - entry) * qty
        else:
            pnl = (entry - exit_price) * qty
        fees = fee_estimate(qty, entry, exit_price, settings.estimated_maker_fee,
                            settings.estimated_taker_fee, settings.estimated_slippage)
        realized = pnl - fees
        self.storage.close_trade(trade_id, str(realized), str(fees))
        self.storage.log_event("EXECUTER", symbol, "paper_close", reason, f"pnl={realized} fees={fees}")
        self.storage.upsert_agent_status("EXECUTER", "MONITORING", current_activity=f"closed {symbol}")
        return {"ok": True, "trade_id": trade_id, "realized_pnl": str(realized), "fees": str(fees), "exit_price": str(exit_price)}

    def monitor(self, client) -> list[dict]:
        actions = []
        for t in self.storage.open_positions():
            price = self._current_price(client, t["symbol"])
            if price is None:
                self.storage.log_event("EXECUTER", t["symbol"], "monitor", "stale", "price unavailable")
                continue
            sl = Decimal(str(t["stop_loss"]))
            tp = Decimal(str(t["take_profit"]))
            direction = t["direction"]
            hit_sl = (direction == "LONG" and price <= sl) or (direction == "SHORT" and price >= sl)
            hit_tp = (direction == "LONG" and price >= tp) or (direction == "SHORT" and price <= tp)
            if hit_sl:
                res = self.close_position(t["id"], price, "stop_loss")
                actions.append({"trade_id": t["id"], "action": "stop_loss", **res})
            elif hit_tp:
                res = self.close_position(t["id"], price, "take_profit")
                actions.append({"trade_id": t["id"], "action": "take_profit", **res})
        return actions

    def account_summary(self, client=None) -> dict:
        eq = self.storage.equity_summary()
        starting = settings.simulated_starting_balance
        realized = Decimal(str(eq.get("realized_pnl", 0)))
        fees = Decimal(str(eq.get("fees", 0)))
        equity = starting + realized
        # unrealized
        unrealized = Decimal("0")
        positions = self.storage.open_positions()
        prices = {}
        if client is not None:
            for p in positions:
                pr = self._current_price(client, p["symbol"])
                if pr is not None:
                    prices[p["symbol"]] = pr
                    qty = Decimal(str(p["quantity"]))
                    entry = Decimal(str(p["entry_price"]))
                    if p["direction"] == "LONG":
                        unrealized += (pr - entry) * qty
                    else:
                        unrealized += (entry - pr) * qty
        return {
            "starting_balance": str(starting),
            "realized_pnl": str(realized),
            "unrealized_pnl": str(unrealized),
            "fees": str(fees),
            "equity": str(equity + unrealized),
            "open_positions": len(positions),
            "prices": {k: str(v) for k, v in prices.items()},
            "stale": client is None or len(prices) < len(positions),
        }