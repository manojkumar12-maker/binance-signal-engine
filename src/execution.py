"""Execution lifecycle and protective-order verification.

Binance Demo (testnet) execution is enabled in paper mode when testnet keys
are configured. Live execution additionally requires all live flags plus the
data/LIVE_ACTIVATED marker file.
"""
import hashlib
import os
import time
from decimal import Decimal
from .binance_client import BinanceClient
from .config import settings
from .risk_engine import size_position, TradeProposal
from .exchange_filters import (
    validate_order, round_quantity, round_price, get_lot_size_filter, get_price_filter,
)
from .account import (
    has_open_position, has_open_position_for_symbol, get_available_equity, open_entry_orders,
)
from .storage import Storage
from .kill_switch import KillSwitch

LIVE_MARKER = os.path.join("data", "LIVE_ACTIVATED")


def exchange_execution_authorized() -> bool:
    """True when orders may be placed on Binance Demo or (gated) live."""
    if settings.testnet_execution_ready:
        return True
    if settings.live_authorized:
        return os.path.exists(LIVE_MARKER)
    return False


class ExecutionEngine:
    def __init__(self, client: BinanceClient, storage: Storage, exchange_info: dict):
        self.client = client
        self.storage = storage
        self.exchange_info = exchange_info
        self._lock = False
        self._dual_side = None

    def _acquire_lock(self) -> bool:
        if self._lock:
            return False
        self._lock = True
        return True

    def _release_lock(self):
        self._lock = False

    def _is_dual_side(self) -> bool:
        """Detect Hedge Mode once; default to One-way Mode on any error."""
        if self._dual_side is None:
            probe = getattr(self.client, "position_mode_dual", None)
            try:
                self._dual_side = bool(probe()) if probe else False
            except Exception:
                self._dual_side = False
        return self._dual_side

    def _side_params(self, direction: str) -> dict:
        return {"positionSide": direction} if self._is_dual_side() else {}

    def can_enter(self, symbol: str) -> tuple[bool, str]:
        if settings.max_simultaneous_positions <= len(self.storage.open_positions()):
            return False, "max positions reached"
        if has_open_position_for_symbol(self.client, symbol):
            return False, "exchange shows open position for symbol"
        if open_entry_orders(self.client, symbol):
            return False, "open entry orders exist"
        halted, reason = self.storage.is_halted()
        if halted:
            return False, f"kill switch halted: {reason}"
        return True, "ok"

    def _client_order_id(self, signal, symbol: str) -> str:
        raw = getattr(signal, "signal_id", "") or f"{symbol}:{getattr(signal, 'direction', '')}:{time.time()}"
        digest = hashlib.md5(raw.encode()).hexdigest()[:30]
        return f"bse-{digest}"

    def _stop_price(self, symbol: str, price) -> Decimal:
        value = Decimal(str(price))
        pf = get_price_filter(self.exchange_info, symbol)
        if pf:
            tick = Decimal(str(pf.get("tickSize", "0")))
            if tick > 0:
                value = round_price(value, tick)
        return value

    def _place_protective_stop(self, symbol: str, direction: str, stop_loss) -> dict:
        side = "SELL" if direction == "LONG" else "BUY"
        return self.client.place_order(
            symbol=symbol,
            side=side,
            type="STOP_MARKET",
            stopPrice=str(self._stop_price(symbol, stop_loss)),
            closePosition="true",
            workingType="MARK_PRICE",
            **self._side_params(direction),
        )

    def _place_take_profit(self, symbol: str, direction: str, take_profit) -> dict:
        side = "SELL" if direction == "LONG" else "BUY"
        return self.client.place_order(
            symbol=symbol,
            side=side,
            type="TAKE_PROFIT_MARKET",
            stopPrice=str(self._stop_price(symbol, take_profit)),
            closePosition="true",
            workingType="MARK_PRICE",
            **self._side_params(direction),
        )

    def execute_signal(self, signal, symbol: str, size_decision=None) -> tuple[bool, str]:
        if not self._acquire_lock():
            return False, "execution lock held"
        try:
            ok, reason = self.can_enter(symbol)
            if not ok:
                self.storage.log_event("EXECUTER", symbol, "can_enter", "rejected", reason)
                return False, reason

            if size_decision is not None and getattr(size_decision, "quantity", None) is not None:
                qty = Decimal(str(size_decision.quantity))
                if qty <= 0:
                    self.storage.log_event("SIZER", symbol, "size", "rejected", "no valid quantity")
                    return False, "risk rejected: no valid quantity"
                self.storage.log_event("SIZER", symbol, "size", "approved", f"qty={qty}")
            else:
                available = get_available_equity(self.client)
                proposal = TradeProposal(
                    symbol=symbol,
                    direction=signal.direction,
                    entry_price=signal.entry_price,
                    stop_loss_price=signal.stop_loss,
                    take_profit_price=signal.take_profit,
                    leverage=settings.max_leverage,
                )
                decision = size_position(proposal, available)
                if not decision.approved:
                    self.storage.log_event("SIZER", symbol, "size", "rejected", decision.reason)
                    return False, f"risk rejected: {decision.reason}"
                qty = decision.quantity
                self.storage.log_event("SIZER", symbol, "size", "approved", f"qty={qty} risk={decision.estimated_loss}")

            lot = get_lot_size_filter(self.exchange_info, symbol)
            if lot:
                qty = round_quantity(qty, Decimal(str(lot["stepSize"])))
            okf, freason = validate_order(self.exchange_info, symbol, qty, signal.entry_price)
            if not okf:
                self.storage.log_event("EXECUTER", symbol, "filter", "rejected", freason)
                return False, f"filter rejected: {freason}"

            if not exchange_execution_authorized():
                self.storage.save_signal(signal, accepted=False, reason="execution disabled; recorded only")
                self.storage.log_event("EXECUTER", symbol, "execution", "recorded", "Binance execution disabled")
                return True, "recorded (execution disabled)"

            try:
                self.client.set_leverage(symbol, settings.max_leverage)
            except Exception as e:
                self.storage.log_event("EXECUTER", symbol, "leverage", "warning", str(e))

            side = "BUY" if signal.direction == "LONG" else "SELL"
            client_order_id = self._client_order_id(signal, symbol)
            entry_kwargs: dict = {
                "symbol": symbol,
                "side": side,
                "type": "MARKET",
                "quantity": str(qty),
                "newOrderRespType": "RESULT",
                "newClientOrderId": client_order_id,
            }
            if self._is_dual_side():
                entry_kwargs["positionSide"] = signal.direction
            else:
                entry_kwargs["reduceOnly"] = False
            entry_resp = self.client.place_order(**entry_kwargs)
            order_id = entry_resp.get("orderId")
            filled_qty = Decimal(str(entry_resp.get("executedQty") or "0"))
            avg_price = Decimal(str(entry_resp.get("avgPrice") or "0"))
            if filled_qty <= 0 and order_id:
                try:
                    queried = self.client.query_order(symbol, order_id)
                    filled_qty = Decimal(str(queried.get("executedQty") or "0"))
                    avg_price = Decimal(str(queried.get("avgPrice") or "0"))
                except Exception:
                    pass
            if filled_qty <= 0:
                return False, "entry not filled"

            if avg_price <= 0:
                try:
                    avg_price = self.client.ticker_price(symbol)
                except Exception:
                    avg_price = Decimal(str(signal.entry_price))

            stop_resp = self._place_protective_stop(symbol, signal.direction, signal.stop_loss)
            stop_id = stop_resp.get("orderId")
            if not stop_id:
                self._emergency_close(symbol, signal.direction, filled_qty)
                self.storage.set_halted(True, "protective stop failed")
                return False, "protective stop failed; halted"

            try:
                self._place_take_profit(symbol, signal.direction, signal.take_profit)
            except Exception as e:
                # The protective stop is already live; a missing TP is not
                # fatal but must be visible in the event log.
                self.storage.log_event("EXECUTER", symbol, "take_profit", "warning", str(e))

            trade = {
                "symbol": symbol,
                "direction": signal.direction,
                "entry_price": avg_price,
                "stop_loss": signal.stop_loss,
                "take_profit": signal.take_profit,
                "quantity": filled_qty,
                "entry_order_id": str(order_id),
                "stop_order_id": str(stop_id),
            }
            self.storage.open_trade(trade)
            self.storage.save_signal(signal, accepted=True)
            self.storage.log_event(
                "EXECUTER", symbol, "execution", "executed",
                f"order={order_id} qty={filled_qty} entry={avg_price} stop={stop_id}",
            )
            return True, "executed"
        except Exception as e:
            return False, f"execution error: {e}"
        finally:
            self._release_lock()

    def _realized_pnl(self, trade) -> tuple[Decimal, Decimal, Decimal, bool]:
        """Return (pnl, fees, funding, ok). ok=False when income is unavailable."""
        pnl = Decimal("0")
        fees = Decimal("0")
        funding = Decimal("0")
        try:
            rows = self.client.income(symbol=trade["symbol"], start_time=trade.get("opened_at"))
        except Exception as e:
            self.storage.log_event("EXECUTER", trade.get("symbol", ""), "income", "error", str(e))
            return pnl, fees, funding, False
        for row in rows:
            income = Decimal(str(row.get("income", "0")))
            if row.get("incomeType") == "REALIZED_PNL":
                pnl += income
            elif row.get("incomeType") == "COMMISSION":
                fees += abs(income)
            elif row.get("incomeType") == "FUNDING_FEE":
                funding += income
        return pnl, fees, funding, True

    def monitor(self) -> list[dict]:
        """Sync local exchange-executed trades and ensure protective stops exist."""
        actions: list[dict] = []
        trades = self.storage.open_positions()
        if not trades:
            return actions
        try:
            positions = self.client.position_risk()
        except Exception as e:
            self.storage.log_event("EXECUTER", "", "monitor", "error", f"position fetch failed: {e}")
            return actions
        amounts = {p.get("symbol"): Decimal(str(p.get("positionAmt", "0"))) for p in positions}
        for t in trades:
            if amounts.get(t["symbol"], Decimal("0")) == 0:
                pnl, fees, funding, ok = self._realized_pnl(t)
                self.storage.close_trade(t["id"], str(pnl), str(fees), str(funding))
                net = pnl + funding - fees
                if ok:
                    KillSwitch(self.storage).record_trade_result(net)
                else:
                    # Do not silently under-count losses if income is missing.
                    self.storage.log_event(
                        "EXECUTER", t["symbol"], "monitor", "warning",
                        "income unavailable; daily loss not updated for this trade")
                self.storage.log_event(
                    "EXECUTER", t["symbol"], "monitor", "closed",
                    f"closed on exchange pnl={pnl} fees={fees} funding={funding} net={net}",
                )
                actions.append({"trade_id": t["id"], "action": "closed_on_exchange",
                                "realized_pnl": str(net), "fees": str(fees), "funding": str(funding)})
                continue
            try:
                orders = self.client.open_orders(t["symbol"])
                has_stop = any(
                    o.get("type") in ("STOP_MARKET", "STOP")
                    and (o.get("closePosition") is True
                         or str(o.get("closePosition")).lower() == "true"
                         or o.get("reduceOnly") is True)
                    for o in orders
                )
                if not has_stop:
                    resp = self._place_protective_stop(t["symbol"], t["direction"], t["stop_loss"])
                    if resp.get("orderId"):
                        self.storage.update_trade_stop_order(t["id"], str(resp["orderId"]))
                        self.storage.log_event("EXECUTER", t["symbol"], "monitor", "stop_replaced",
                                               f"stop={resp['orderId']}")
                        actions.append({"trade_id": t["id"], "action": "stop_replaced"})
                    else:
                        self.storage.set_halted(True, "protective stop missing")
                        actions.append({"trade_id": t["id"], "action": "stop_failed"})
            except Exception as e:
                self.storage.log_event("EXECUTER", t["symbol"], "monitor", "error", str(e))
        return actions

    def _emergency_close(self, symbol: str, direction: str, qty: Decimal):
        side = "SELL" if direction == "LONG" else "BUY"
        kwargs: dict = {"symbol": symbol, "side": side, "type": "MARKET", "quantity": str(qty)}
        if self._is_dual_side():
            kwargs["positionSide"] = direction
        else:
            kwargs["reduceOnly"] = True
        try:
            self.client.place_order(**kwargs)
        except Exception:
            pass
        try:
            if has_open_position(self.client):
                self.storage.set_halted(True, "emergency close unverified")
        except Exception:
            self.storage.set_halted(True, "emergency close verification failed")

    def reconcile(self) -> None:
        # Sync storage open trades with exchange positions
        try:
            ex_positions = self.client.position_risk()
        except Exception:
            return
        ex_map = {p["symbol"]: Decimal(str(p.get("positionAmt", "0"))) for p in ex_positions}
        for t in self.storage.open_positions():
            amt = ex_map.get(t["symbol"], Decimal("0"))
            if amt == 0:
                # position closed on exchange; mark closed
                self.storage.close_trade(t["id"], "0", "0")
