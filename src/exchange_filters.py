"""Exchange filter validation using Decimal arithmetic."""
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP, InvalidOperation
from typing import Optional, Dict


def _get_filter(info: dict, filter_type: str, symbol: str) -> Optional[dict]:
    for s in info.get("symbols", []):
        if s.get("symbol") == symbol:
            for f in s.get("filters", []):
                if f.get("filterType") == filter_type:
                    return f
    return None


def get_symbol_info(info: dict, symbol: str) -> Optional[dict]:
    for s in info.get("symbols", []):
        if s.get("symbol") == symbol:
            return s
    return None


def validate_symbol_status(info: dict, symbol: str) -> bool:
    si = get_symbol_info(info, symbol)
    if not si:
        return False
    return si.get("status") == "TRADING"


def round_quantity(qty: Decimal, step_size: Decimal) -> Decimal:
    if step_size <= 0:
        raise ValueError("invalid step size")
    return (qty / step_size).to_integral_value(rounding=ROUND_DOWN) * step_size


def round_price(price: Decimal, tick_size: Decimal) -> Decimal:
    if tick_size <= 0:
        raise ValueError("invalid tick size")
    return (price / tick_size).to_integral_value(rounding=ROUND_HALF_UP) * tick_size


def get_lot_size_filter(info, symbol):
    return _get_filter(info, "LOT_SIZE", symbol)


def get_price_filter(info, symbol):
    return _get_filter(info, "PRICE_FILTER", symbol)


def get_min_notional_filter(info, symbol):
    return _get_filter(info, "MIN_NOTIONAL", symbol)


def validate_order(info: dict, symbol: str, quantity: Decimal, price: Optional[Decimal] = None) -> tuple[bool, str]:
    if not validate_symbol_status(info, symbol):
        return False, "contract not trading or unknown"
    lot = get_lot_size_filter(info, symbol)
    if lot:
        min_qty = Decimal(lot["minQty"])
        max_qty = Decimal(lot["maxQty"])
        step = Decimal(lot["stepSize"])
        if quantity < min_qty:
            return False, f"quantity below min {min_qty}"
        if quantity > max_qty:
            return False, f"quantity above max {max_qty}"
        rounded = round_quantity(quantity, step)
        if rounded != quantity:
            return False, "quantity not aligned to step size"
    pf = get_price_filter(info, symbol)
    if pf and price is not None:
        tick = Decimal(pf["tickSize"])
        if round_price(price, tick) != price:
            return False, "price not aligned to tick size"
    mn = get_min_notional_filter(info, symbol)
    if mn and price is not None:
        min_notional = Decimal(mn.get("notional", mn.get("minNotional", "0")))
        if quantity * price < min_notional:
            return False, f"notional below minimum {min_notional}"
    return True, "ok"