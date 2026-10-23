"""Reconciliation between local storage and Binance exchange state."""
from decimal import Decimal
from .binance_client import BinanceClient
from .storage import Storage


class ReconciliationService:
    def __init__(self, client: BinanceClient, storage: Storage):
        self.client = client
        self.storage = storage

    def reconcile(self) -> dict:
        result = {"positions_synced": 0, "orders_synced": 0, "discrepancies": []}
        try:
            ex_positions = self.client.position_risk()
        except Exception as e:
            result["discrepancies"].append(f"position fetch failed: {e}")
            return result
        ex_map = {p["symbol"]: Decimal(str(p.get("positionAmt", "0"))) for p in ex_positions}

        # mark locally open trades that are closed on exchange
        for t in self.storage.open_positions():
            amt = ex_map.get(t["symbol"], Decimal("0"))
            if amt == 0:
                self.storage.close_trade(t["id"], "0", "0")
                result["discrepancies"].append(f"local open but exchange closed: {t['symbol']}")

        # unknown exchange positions
        local_symbols = {t["symbol"] for t in self.storage.open_positions()}
        for sym, amt in ex_map.items():
            if amt != 0 and sym not in local_symbols:
                result["discrepancies"].append(f"unknown exchange position: {sym} {amt}")

        try:
            open_orders = self.client.open_orders()
        except Exception as e:
            result["discrepancies"].append(f"orders fetch failed: {e}")
            return result
        result["orders_synced"] = len(open_orders)
        result["positions_synced"] = len(ex_positions)
        return result