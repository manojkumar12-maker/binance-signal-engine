"""Paper trading engine (simulated execution)."""
from decimal import Decimal
from .storage import Storage
from .config import settings
from .risk_engine import fee_estimate
from .kill_switch import KillSwitch


class PaperTrader:
    def __init__(self, storage: Storage):
        self.storage = storage
        self.kill = KillSwitch(storage)

    def _current_price(self, client, symbol):
        try:
            return client.ticker_price(symbol)
        except Exception:
            return None

    def open_position(self, client, trade_proposal, size_decision, signal) -> dict:
        symbol = trade_proposal["symbol"] if isinstance(trade_proposal, dict) else trade_proposal.symbol
        open_positions = self.storage.open_positions()
        if any(p["symbol"] == symbol for p in open_positions):
            return {"ok": False, "reason": "position already open for symbol"}
        if len(open_positions) >= settings.max_simultaneous_positions:
            return {"ok": False, "reason": "max positions reached"}
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

        # The live price may have drifted from the signal's candle close. A
        # price already at or beyond the planned stop/target would be closed
        # immediately by monitor(), so the trade is not opened at all.
        if direction == "LONG":
            beyond_levels = entry <= sl or entry >= tp
            stop_distance = entry - sl
        else:
            beyond_levels = entry >= sl or entry <= tp
            stop_distance = sl - entry
        if beyond_levels:
            self.storage.log_event("EXECUTER", symbol, "paper_open", "rejected",
                                   f"live price {entry} beyond planned SL {sl} / TP {tp}")
            return {"ok": False, "reason": "live price beyond planned stop/target"}

        # Re-scale the quantity so the planned loss at the live stop distance
        # (plus taker fees both sides) stays within the approved risk budget.
        if isinstance(size_decision, dict):
            risk_amount = size_decision.get("risk_amount", Decimal("0"))
        else:
            risk_amount = getattr(size_decision, "risk_amount", Decimal("0"))
        fee_per_unit = fee_estimate(Decimal("1"), entry, sl, settings.estimated_taker_fee,
                                    settings.estimated_taker_fee, Decimal("0"))
        denom = stop_distance + fee_per_unit
        if risk_amount > 0 and denom > 0 and qty * denom > risk_amount:
            rescaled = (risk_amount / denom)
            # keep the original quantity's precision; round down so risk never
            # grows past the budget
            rescaled = rescaled.quantize(qty, rounding="ROUND_DOWN")
            if rescaled <= 0:
                self.storage.log_event("EXECUTER", symbol, "paper_open", "rejected",
                                       "rescaled quantity below minimum step")
                return {"ok": False, "reason": "risk budget too small for live stop distance"}
            self.storage.log_event("EXECUTER", symbol, "paper_open", "rescaled",
                                   f"qty {qty} -> {rescaled} for live stop distance {stop_distance}")
            qty = rescaled

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
        # Slippage is already applied to entry/exit prices above, so it must
        # not be added again inside the fee estimate.
        fees = fee_estimate(qty, entry, exit_price, settings.estimated_maker_fee,
                            settings.estimated_taker_fee, Decimal("0"))
        realized = pnl - fees
        self.storage.close_trade(trade_id, str(realized), str(fees))
        self.kill.record_trade_result(realized)
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
