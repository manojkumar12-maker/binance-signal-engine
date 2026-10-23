"""Binance USDT-M Futures REST client with signing and server-time sync."""
import hashlib
import hmac
import time
import httpx
from decimal import Decimal
from typing import Any, Optional
from .config import settings


class BinanceClient:
    def __init__(self, api_key: str = "", api_secret: str = "", testnet: bool = True):
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        self.base_url = "https://testnet.binancefuture.com" if testnet else "https://fapi.binance.com"
        self._time_offset_ms = 0
        self._client = httpx.Client(timeout=10.0)

    def sync_time(self) -> None:
        r = self._client.get(f"{self.base_url}/fapi/v1/time")
        r.raise_for_status()
        server_time = r.json()["serverTime"]
        self._time_offset_ms = server_time - int(time.time() * 1000)

    def _timestamp(self) -> int:
        return int(time.time() * 1000) + self._time_offset_ms

    def _sign(self, params: dict) -> str:
        query = "&".join(f"{k}={v}" for k, v in params.items())
        return hmac.new(self.api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()

    def _request(self, method: str, path: str, params: Optional[dict] = None, signed: bool = False) -> Any:
        params = dict(params or {})
        headers = {}
        if self.api_key:
            headers["X-MBX-APIKEY"] = self.api_key
        if signed:
            params["timestamp"] = self._timestamp()
            params["recvWindow"] = 5000
            params["signature"] = self._sign(params)
        url = f"{self.base_url}{path}"
        if method == "GET":
            r = self._client.get(url, params=params, headers=headers)
        elif method == "POST":
            r = self._client.post(url, params=params, headers=headers)
        elif method == "DELETE":
            r = self._client.delete(url, params=params, headers=headers)
        else:
            raise ValueError(method)
        r.raise_for_status()
        return r.json()

    # Market data
    def exchange_info(self) -> dict:
        return self._request("GET", "/fapi/v1/exchangeInfo")

    def ticker_price(self, symbol: str) -> Decimal:
        data = self._request("GET", "/fapi/v1/ticker/price", {"symbol": symbol})
        return Decimal(str(data["price"]))

    def klines(self, symbol: str, interval: str, limit: int = 200) -> list:
        return self._request("GET", "/fapi/v1/klines", {"symbol": symbol, "interval": interval, "limit": limit})

    def funding_rate(self, symbol: str) -> Decimal:
        data = self._request("GET", "/fapi/v1/premiumIndex", {"symbol": symbol})
        return Decimal(str(data.get("lastFundingRate", "0")))

    # Account
    def account(self) -> dict:
        return self._request("GET", "/fapi/v2/account", signed=True)

    def position_risk(self) -> list:
        return self._request("GET", "/fapi/v2/positionRisk", signed=True)

    def open_orders(self, symbol: Optional[str] = None) -> list:
        params = {"symbol": symbol} if symbol else {}
        return self._request("GET", "/fapi/v1/openOrders", params, signed=True)

    # Orders
    def place_order(self, **kwargs) -> dict:
        return self._request("POST", "/fapi/v1/order", kwargs, signed=True)

    def cancel_order(self, symbol: str, order_id: int) -> dict:
        return self._request("DELETE", "/fapi/v1/order", {"symbol": symbol, "orderId": order_id}, signed=True)

    def query_order(self, symbol: str, order_id: int) -> dict:
        return self._request("GET", "/fapi/v1/order", {"symbol": symbol, "orderId": order_id}, signed=True)

    def close(self) -> None:
        self._client.close()