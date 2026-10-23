"""Execution lifecycle and protective-order verification."""
from decimal import Decimal
from typing import Optional, Dict
from .binance_client import BinanceClient
from .config import settings
from .risk_engine import size_position, TradeProposal
from .exchange_filters import validate_order, round_quantity
from .account import has_open_position, get_available_equity, open_entry_orders
from .storage import Storage


class ExecutionEngine:
    def __init__(self, client: BinanceClient, storage: Storage, exchange_info: dict):
        self.client = client
        self.storage = storage
        self.exchange_info = exchange_info
        self._lock = False

    def _acquire_lock(self) -> bool:
        if self._lock:
            return False
        self._lock = True
        return True

    def _release_lock(self):
        self._lock = False

    def can_enter(self, symbol: str) -> tuple[bool, str]:
        if settings.max_simultaneous_positions <= len(self.storage.open_positions()):
            return False, "max positions reached"
        if has_open_position(self.client):
            return False, "exchange shows open position"
        if open_entry_orders(self.client, symbol):
            return False, "open entry orders exist"
        halted, reason = self.storage.is_halted()
        if halted:
            return False, f"kill switch halted: {reason}"
        return True, "ok"

    def execute_signal(self, signal, symbol: str) -> tuple[bool, str]:
        if not self._acquire_lock():
            return False, "execution lock held"
        try:
            ok, reason = self.can_enter(symbol)
            if not ok:
                return False, reason

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
                return False, f"risk rejected: {decision.reason}"

            from src.exchange_filters import get_lot_size_filter, round_quantity
            from decimal import Decimal as _D
            qty = decision.quantity
            lot = get_lot_size_filter(self.exchange_info, symbol)
            if lot:
                step = _D(lot["stepSize"])
                qty = round_quantity(qty, step)
            # validate quantity with exchange filters
            okf, freason = validate_order(self.exchange_info, symbol, qty, signal.entry_price)
            if not okf:
                return False, f"filter rejected: {freason}"

            # Live trading gate (multiple independent checks + activation marker file)
            import os
            activation_marker = os.path.join("data", "LIVE_ACTIVATED")
            if not (settings.live_authorized and os.path.exists(activation_marker)):
                self.storage.save_signal(signal, accepted=False, reason="live not authorized; recorded only")
                return True, "recorded (live disabled)"

            # Place entry order (market)
            side = "BUY" if signal.direction == "LONG" else "SELL"
            entry_resp = self.client.place_order(
                symbol=symbol, side=side, type="MARKET", quantity=str(qty), reduceOnly=False,
            )
            order_id = entry_resp.get("orderId")
            # Verify fill
            filled_qty = Decimal(str(entry_resp.get("executedQty", qty)))
            if filled_qty <= 0:
                return False, "entry not filled"

            # Place protective stop (stop market, reduce only)
            stop_side = "SELL" if signal.direction == "LONG" else "BUY"
            stop_resp = self.client.place_order(
                symbol=symbol, side=stop_side, type="STOP_MARKET",
                stopPrice=str(signal.stop_loss), closePosition="true", reduceOnly=True,
            )
            stop_id = stop_resp.get("orderId")
            if not stop_id:
                # emergency close
                self._emergency_close(symbol, signal.direction, filled_qty)
                self.storage.set_halted(True, "protective stop failed")
                return False, "protective stop failed; halted"

            # Optional take profit
            tp_side = "SELL" if signal.direction == "LONG" else "BUY"
            try:
                self.client.place_order(
                    symbol=symbol, side=tp_side, type="TAKE_PROFIT_MARKET",
                    stopPrice=str(signal.take_profit), closePosition="true", reduceOnly=True,
                )
            except Exception:
                pass  # non-fatal

            trade = {
                "symbol": symbol,
                "direction": signal.direction,
                "entry_price": signal.entry_price,
                "stop_loss": signal.stop_loss,
                "take_profit": signal.take_profit,
                "quantity": filled_qty,
                "entry_order_id": str(order_id),
                "stop_order_id": str(stop_id),
            }
            self.storage.open_trade(trade)
            self.storage.save_signal(signal, accepted=True)
            return True, "executed"
        except Exception as e:
            return False, f"execution error: {e}"
        finally:
            self._release_lock()

    def _emergency_close(self, symbol: str, direction: str, qty: Decimal):
        side = "SELL" if direction == "LONG" else "BUY"
        try:
            self.client.place_order(symbol=symbol, side=side, type="MARKET", quantity=str(qty), reduceOnly=True)
        except Exception:
            pass
        # verify
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