"""Mock Binance client for unit tests."""
from decimal import Decimal
from unittest.mock import MagicMock


class MockBinanceClient:
    def __init__(self):
        self.server_time = 1700000000000
        self.exchange_info_data = {
            "symbols": [
                {
                    "symbol": "BTCUSDT",
                    "status": "TRADING",
                    "filters": [
                        {"filterType": "LOT_SIZE", "minQty": "0.00001", "maxQty": "1000", "stepSize": "0.00001"},
                        {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                        {"filterType": "MIN_NOTIONAL", "notional": "1"},
                    ],
                }
            ]
        }
        self.account_data = {"availableBalance": "5.0", "totalWalletBalance": "5.0"}
        self.positions = []
        self.open_orders_list = []
        self.placed_orders = []
        self._order_id = 1000

    def sync_time(self):
        pass

    def exchange_info(self):
        return self.exchange_info_data

    def ticker_price(self, symbol):
        return Decimal("50000")

    def klines(self, symbol, interval, limit=200):
        # flat-ish series with slight trend
        base = Decimal("50000")
        out = []
        for i in range(limit):
            p = base + Decimal(i) * Decimal("0.5")
            out.append([0, str(p), str(p), str(p), str(p), "1"])
        return out

    def account(self):
        return self.account_data

    def position_risk(self):
        return self.positions

    def open_orders(self, symbol=None):
        if symbol:
            return [o for o in self.open_orders_list if o.get("symbol") == symbol]
        return self.open_orders_list

    def place_order(self, **kwargs):
        self._order_id += 1
        resp = {"orderId": self._order_id, "executedQty": kwargs.get("quantity", "0"), "status": "FILLED"}
        self.placed_orders.append({"id": self._order_id, **kwargs})
        return resp

    def close(self):
        pass