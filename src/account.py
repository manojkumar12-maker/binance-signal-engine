"""Account state retrieval and validation."""
from decimal import Decimal
from .binance_client import BinanceClient


def get_available_equity(client: BinanceClient) -> Decimal:
    acct = client.account()
    # availableBalance is margin-available; totalWalletBalance includes unrealized.
    avail = Decimal(str(acct.get("availableBalance", "0")))
    return avail


def account_snapshot(client: BinanceClient) -> dict:
    """Normalized account balances for dashboard/equity display."""
    acct = client.account()
    balance = Decimal(str(acct.get("totalWalletBalance", "0")))
    unrealized = Decimal(str(acct.get("totalUnrealizedProfit", "0")))
    margin = Decimal(str(acct.get("totalMarginBalance", "0")))
    equity = margin if margin > 0 else balance + unrealized
    return {
        "equity": str(equity),
        "balance": str(balance),
        "available": str(Decimal(str(acct.get("availableBalance", "0")))),
        "unrealized": str(unrealized),
        "can_trade": bool(acct.get("canTrade", False)),
        "can_withdraw": bool(acct.get("canWithdraw", False)),
    }


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