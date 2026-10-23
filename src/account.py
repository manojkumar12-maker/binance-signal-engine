"""Account state retrieval and validation."""
from decimal import Decimal
from typing import Optional
from .binance_client import BinanceClient


def get_available_equity(client: BinanceClient) -> Decimal:
    acct = client.account()
    # availableBalance is margin-available; totalWalletBalance includes unrealized.
    avail = Decimal(str(acct.get("availableBalance", "0")))
    return avail


def get_positions(client: BinanceClient) -> list[dict]:
    return client.position_risk()


def has_open_position(client: BinanceClient) -> bool:
    for p in get_positions(client):
        if Decimal(str(p.get("positionAmt", "0"))) != 0:
            return True
    return False


def open_entry_orders(client: BinanceClient, symbol: str) -> list[dict]:
    orders = client.open_orders(symbol)
    return [o for o in orders if o.get("reduceOnly") is not True and o.get("type") in ("MARKET", "LIMIT")]