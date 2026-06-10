import config
from typing import Dict, Tuple, Optional


def check_entry_slippage(
    signal_entry: float,
    current_price: float,
    max_slippage_pct: float = None,
    signal_type: str = "BUY"
) -> Tuple[bool, str]:
    if max_slippage_pct is None:
        max_slippage_pct = config.MAX_ENTRY_SLIPPAGE
    
    if signal_entry <= 0 or current_price <= 0:
        return True, "NO_PRICE"
    
    slippage = abs(current_price - signal_entry) / signal_entry
    
    if slippage > max_slippage_pct:
        return False, f"SLIPPAGE_TOO_HIGH ({slippage*100:.2f}% > {max_slippage_pct*100}%)"
    
    return True, "OK"


def calculate_adjusted_entry(
    signal_entry: float,
    current_price: float,
    signal_type: str,
    use_limit: bool = True
) -> float:
    if signal_type == "BUY":
        if current_price < signal_entry:
            return current_price if use_limit else signal_entry
        else:
            return signal_entry
    else:
        if current_price > signal_entry:
            return current_price if use_limit else signal_entry
        else:
            return signal_entry


def validate_execution(
    signal: Dict,
    current_price: float,
    max_slippage_pct: float = None
) -> Tuple[bool, str]:
    entry = signal.get("entry_primary", 0)
    signal_type = signal.get("signal", "BUY")
    
    if entry <= 0 or current_price <= 0:
        return True, "VALIDATE_SKIP"
    
    is_valid, reason = check_entry_slippage(entry, current_price, max_slippage_pct, signal_type)
    
    return is_valid, reason


def get_execution_type(signal: Dict, current_price: float) -> str:
    entry = signal.get("entry_primary", 0)
    signal_type = signal.get("signal", "BUY")
    
    if entry <= 0:
        return "UNKNOWN"
    
    slippage = abs(current_price - entry) / entry
    
    if slippage < 0.001:
        return "MARKET"
    elif slippage < config.MAX_ENTRY_SLIPPAGE:
        return "LIMIT"
    else:
        return "SKIP"
