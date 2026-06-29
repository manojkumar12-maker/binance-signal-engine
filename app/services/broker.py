import time
import logging
import asyncio
from typing import Dict, Optional
from datetime import datetime, timedelta
from decimal import Decimal

import config
from app.services.risk_engine import get_dynamic_risk

logger = logging.getLogger("broker")

_client = None
_client_lock = asyncio.Lock()
_last_order_ts = 0.0
_RATE_LIMIT_DELAY = 0.1

class BrokerError(Exception):
    pass

class KillSwitchError(BrokerError):
    pass

class OrderRejectedError(BrokerError):
    pass

def _get_client():
    global _client
    if _client is not None:
        return _client
    from binance.futures import Futures as Client
    base_url = config.FUTURES_TESTNET_URL if config.USE_TESTNET else config.FUTURES_API_URL
    _client = Client(
        key=config.BINANCE_API_KEY,
        secret=config.BINANCE_API_SECRET,
        base_url=base_url
    )
    logger.info(f"[BROKER] Initialized {'testnet' if config.USE_TESTNET else 'mainnet'} client")
    return _client

def _rate_limit():
    global _last_order_ts
    now = time.time()
    elapsed = now - _last_order_ts
    if elapsed < _RATE_LIMIT_DELAY:
        time.sleep(_RATE_LIMIT_DELAY - elapsed)
    _last_order_ts = time.time()

def _kill_switch_gate() -> None:
    from app.services import tracker
    analytics = tracker.get_analytics()
    total_trades = analytics.get("total_trades", 0)
    if total_trades < 5:
        return
    drawdown = analytics.get("max_drawdown_pct", 0)
    if drawdown >= config.KILL_SWITCH_DRAWDOWN * 100:
        raise KillSwitchError(
            f"Kill switch: drawdown {drawdown:.1f}% >= {config.KILL_SWITCH_DRAWDOWN * 100}%"
        )
    from datetime import datetime, timedelta
    closed = [t for t in tracker.load_trades() if t.get("closed_at") and t.get("status") != "OPEN"]
    today_loss = 0
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    for t in closed:
        try:
            closed_at = t.get("closed_at", "")
            if closed_at:
                closed_dt = datetime.fromisoformat(closed_at.replace("Z", "+00:00"))
                if closed_dt >= today_start and t.get("pnl_pct", 0) < 0:
                    today_loss += abs(t["pnl_pct"])
        except Exception:
            continue
    if today_loss >= config.KILL_SWITCH_DAILY_LOSS * 100:
        raise KillSwitchError(
            f"Kill switch: daily loss {today_loss:.1f}% >= {config.KILL_SWITCH_DAILY_LOSS * 100}%"
        )

def _build_client_order_id(pair: str, side: str) -> str:
    ts = int(time.time() * 1000)
    return f"sig_{pair}_{side}_{ts}"

def _sync_request(client_method, *args, **kwargs):
    _rate_limit()
    try:
        result = client_method(*args, **kwargs)
        return result
    except Exception as e:
        err_msg = str(e)
        if "-2010" in err_msg or "insufficient balance" in err_msg.lower():
            raise OrderRejectedError(f"Insufficient balance: {err_msg}")
        if "-2011" in err_msg or "cancelled" in err_msg.lower():
            raise OrderRejectedError(f"Order rejected/cancelled: {err_msg}")
        raise BrokerError(f"Binance API error: {err_msg}")

def get_account_balance_sync() -> float:
    if not config.BROKER_ENABLED:
        return config.INITIAL_BALANCE
    client = _get_client()
    try:
        account = client.account()
        for asset in account.get("assets", []):
            if asset.get("asset") == "USDT":
                return float(asset.get("walletBalance", 0))
        return 0.0
    except Exception as e:
        logger.error(f"[BROKER] Failed to fetch balance: {e}")
        return config.INITIAL_BALANCE

def get_position_sync(pair: str) -> Dict:
    if not config.BROKER_ENABLED:
        return {"pair": pair, "positionAmt": 0, "entryPrice": 0, "unRealizedProfit": 0, "leverage": 1}
    client = _get_client()
    try:
        positions = client.account().get("positions", [])
        for pos in positions:
            if pos.get("symbol") == pair:
                return {
                    "pair": pair,
                    "positionAmt": float(pos.get("positionAmt", 0)),
                    "entryPrice": float(pos.get("entryPrice", 0)),
                    "unRealizedProfit": float(pos.get("unRealizedProfit", 0)),
                    "leverage": int(pos.get("leverage", 1))
                }
    except Exception as e:
        logger.error(f"[BROKER] Failed to get position for {pair}: {e}")
    return {"pair": pair, "positionAmt": 0, "entryPrice": 0, "unRealizedProfit": 0, "leverage": 1}

def place_market_order_sync(pair: str, side: str, quantity: float) -> Dict:
    _kill_switch_gate()
    if not config.BROKER_ENABLED:
        logger.info(f"[BROKER][SIM] MARKET {side} {quantity} {pair}")
        return {"orderId": f"sim_{int(time.time())}", "symbol": pair, "side": side,
                "executedQty": quantity, "cummulativeQuoteQty": 0, "status": "FILLED", "simulated": True}
    client = _get_client()
    client_order_id = _build_client_order_id(pair, side)
    params = {
        "symbol": pair,
        "side": side.upper(),
        "type": "MARKET",
        "quantity": round(quantity, 3),
        "newClientOrderId": client_order_id
    }
    result = _sync_request(client.new_order, **params)
    logger.info(f"[BROKER] MARKET {side} {quantity} {pair} -> orderId={result.get('orderId')}")
    return result

def place_limit_order_sync(pair: str, side: str, quantity: float, price: float) -> Dict:
    _kill_switch_gate()
    if not config.BROKER_ENABLED:
        logger.info(f"[BROKER][SIM] LIMIT {side} {quantity} {pair} @ {price}")
        return {"orderId": f"sim_{int(time.time())}", "symbol": pair, "side": side,
                "price": price, "executedQty": 0, "status": "NEW", "simulated": True}
    client = _get_client()
    client_order_id = _build_client_order_id(pair, side)
    params = {
        "symbol": pair,
        "side": side.upper(),
        "type": "LIMIT",
        "timeInForce": "GTC",
        "quantity": round(quantity, 3),
        "price": round(price, 2),
        "newClientOrderId": client_order_id
    }
    result = _sync_request(client.new_order, **params)
    logger.info(f"[BROKER] LIMIT {side} {quantity} {pair} @ {price} -> orderId={result.get('orderId')}")
    return result

def place_stop_loss_sync(pair: str, side: str, quantity: float, stop_price: float) -> Dict:
    _kill_switch_gate()
    close_side = "SELL" if side.upper() == "BUY" else "BUY"
    if not config.BROKER_ENABLED:
        logger.info(f"[BROKER][SIM] STOP {close_side} {quantity} {pair} @ {stop_price}")
        return {"orderId": f"sim_sl_{int(time.time())}", "symbol": pair, "side": close_side,
                "stopPrice": stop_price, "status": "NEW", "simulated": True}
    client = _get_client()
    client_order_id = _build_client_order_id(pair, "SL")
    params = {
        "symbol": pair,
        "side": close_side,
        "type": "STOP_MARKET",
        "quantity": round(quantity, 3),
        "stopPrice": round(stop_price, 2),
        "newClientOrderId": client_order_id
    }
    result = _sync_request(client.new_order, **params)
    logger.info(f"[BROKER] STOP {close_side} {quantity} {pair} @ {stop_price} -> orderId={result.get('orderId')}")
    return result

def place_take_profit_sync(pair: str, side: str, quantity: float, stop_price: float) -> Dict:
    _kill_switch_gate()
    close_side = "SELL" if side.upper() == "BUY" else "BUY"
    if not config.BROKER_ENABLED:
        logger.info(f"[BROKER][SIM] TP {close_side} {quantity} {pair} @ {stop_price}")
        return {"orderId": f"sim_tp_{int(time.time())}", "symbol": pair, "side": close_side,
                "stopPrice": stop_price, "status": "NEW", "simulated": True}
    client = _get_client()
    client_order_id = _build_client_order_id(pair, "TP")
    params = {
        "symbol": pair,
        "side": close_side,
        "type": "TAKE_PROFIT_MARKET",
        "quantity": round(quantity, 3),
        "stopPrice": round(stop_price, 2),
        "newClientOrderId": client_order_id
    }
    result = _sync_request(client.new_order, **params)
    logger.info(f"[BROKER] TP {close_side} {quantity} {pair} @ {stop_price} -> orderId={result.get('orderId')}")
    return result

def cancel_order_sync(pair: str, order_id: str) -> bool:
    if not config.BROKER_ENABLED:
        logger.info(f"[BROKER][SIM] CANCEL {order_id} {pair}")
        return True
    client = _get_client()
    try:
        client.cancel_order(symbol=pair, orderId=order_id)
        logger.info(f"[BROKER] CANCELLED {order_id} {pair}")
        return True
    except Exception as e:
        logger.error(f"[BROKER] Failed to cancel {order_id} {pair}: {e}")
        return False

async def reconcile_positions():
    if not config.BROKER_ENABLED:
        return
    from app.services import tracker
    open_trades = tracker.get_open_trades()
    if not open_trades:
        return
    client = _get_client()
    try:
        positions = client.account().get("positions", [])
    except Exception as e:
        logger.error(f"[BROKER][RECONCILE] Failed to fetch positions: {e}")
        return
    position_map = {p.get("symbol"): p for p in positions}
    for trade in open_trades:
        pair = trade.get("pair", "")
        pos = position_map.get(pair, {})
        pos_amt = float(pos.get("positionAmt", 0))
        expected_side = 1 if trade.get("type") == "BUY" else -1
        has_position = (pos_amt > 0 and expected_side == 1) or (pos_amt < 0 and expected_side == -1)
        if not has_position and abs(pos_amt) > 0.001:
            logger.warning(f"[BROKER][RECONCILE] MISMATCH {pair}: trade={trade.get('type')} pos_amt={pos_amt}")
    logger.info(f"[BROKER][RECONCILE] Checked {len(open_trades)} open trades against exchange")

def compute_position_size(entry: float, sl: float, confidence: int) -> float:
    balance = get_account_balance_sync()
    risk_pct = get_dynamic_risk(confidence)
    risk_amount = balance * risk_pct
    stop_distance = abs(entry - sl)
    if stop_distance == 0:
        return 0
    qty = risk_amount / stop_distance
    return round(qty, 3)

async def place_market_order(pair: str, side: str, quantity: float) -> Dict:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, place_market_order_sync, pair, side, quantity)

async def place_limit_order(pair: str, side: str, quantity: float, price: float) -> Dict:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, place_limit_order_sync, pair, side, quantity, price)

async def place_stop_loss(pair: str, side: str, quantity: float, stop_price: float) -> Dict:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, place_stop_loss_sync, pair, side, quantity, stop_price)

async def place_take_profit(pair: str, side: str, quantity: float, stop_price: float) -> Dict:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, place_take_profit_sync, pair, side, quantity, stop_price)

async def cancel_order(pair: str, order_id: str) -> bool:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, cancel_order_sync, pair, order_id)

async def get_account_balance() -> float:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, get_account_balance_sync)

async def get_position(pair: str) -> Dict:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, get_position_sync, pair)
