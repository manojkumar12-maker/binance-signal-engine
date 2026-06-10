from typing import List, Dict, Tuple, Optional
from datetime import datetime, timedelta
import logging
import config

logger = logging.getLogger("execution_engine")

EXECUTION_MODES = {
    "SAFE": {"max_slippage": 0.003, "use_limit": True, "split_orders": False},
    "BALANCED": {"max_slippage": 0.005, "use_limit": True, "split_orders": True},
    "AGGRESSIVE": {"max_slippage": 0.008, "use_limit": False, "split_orders": False}
}

SOR_POOL_SIZE = 3


def get_execution_mode(confidence: int, volatility: float) -> str:
    if confidence >= 80 and volatility < 0.005:
        return "SAFE"
    elif confidence >= 70:
        return "BALANCED"
    else:
        return "AGGRESSIVE"


def calculate_slippage_estimate(
    entry: float,
    signal_entry: float,
    signal_type: str,
    volume_24h: float,
    order_book_bid: float,
    order_book_ask: float
) -> Dict:
    base_slippage = abs(entry - signal_entry) / signal_entry if signal_entry > 0 else 0
    
    spread = (order_book_ask - order_book_bid) / entry if entry > 0 else 0
    
    volume_factor = min(1.0, volume_24h / 100000000)
    
    market_impact = volume_factor * 0.001
    
    estimated_slippage = base_slippage + spread / 2 + market_impact
    
    is_acceptable = estimated_slippage <= config.MAX_ENTRY_SLIPPAGE
    
    return {
        "estimated_slippage": round(estimated_slippage * 100, 3),
        "spread": round(spread * 100, 3),
        "market_impact": round(market_impact * 100, 3),
        "acceptable": is_acceptable,
        "recommendation": "MARKET" if is_acceptable else "LIMIT"
    }


def split_order_size(total_size: float, splits: int = 3) -> List[float]:
    if splits <= 1:
        return [total_size]
    
    primary_size = total_size * 0.5
    remaining = total_size - primary_size
    split_size = remaining / (splits - 1)
    
    return [primary_size] + [split_size] * (splits - 1)


def calculate_iceberg_quantity(
    total_size: float,
    visible_liquidity: float,
    max_participation: float = 0.1
) -> float:
    if visible_liquidity <= 0:
        return total_size * max_participation
    
    participation = min(max_participation, total_size / visible_liquidity)
    
    return total_size * participation


def select_best_execution_venue(
    venues: List[Dict],
    side: str,
    quantity: float
) -> Optional[Dict]:
    if not venues:
        return None
    
    best_venue = None
    best_score = float('-inf')
    
    for venue in venues:
        price = venue.get("price", 0)
        available = venue.get("available", 0)
        
        if available < quantity * 0.1:
            continue
        
        score = 0
        if side == "BUY":
            score = -price
        else:
            score = price
        
        depth_score = min(1.0, available / quantity) * 10
        score += depth_score
        
        if score > best_score:
            best_score = score
            best_venue = venue
    
    return best_venue


def calculate_twap_execution(
    signal_entry: float,
    signal_type: str,
    total_quantity: float,
    duration_minutes: int = 60,
    interval_seconds: int = 60
) -> List[Dict]:
    intervals = (duration_minutes * 60) // interval_seconds
    
    if intervals <= 0:
        return []
    
    quantity_per_interval = total_quantity / intervals
    
    executions = []
    for i in range(intervals):
        executions.append({
            "interval": i + 1,
            "quantity": round(quantity_per_interval, 4),
            "type": "TWAP",
            "duration_minutes": duration_minutes
        })
    
    return executions


def optimal_order_type(
    signal: Dict,
    current_price: float,
    order_book: Dict
) -> Tuple[str, float]:
    entry = signal.get("entry_primary", 0)
    signal_type = signal.get("signal", "BUY")
    confidence = signal.get("confidence", 70)
    
    if entry <= 0:
        return "MARKET", 0
    
    slippage = abs(current_price - entry) / entry
    
    mid_price = (order_book.get("ask", entry) + order_book.get("bid", entry)) / 2
    
    if slippage < 0.002:
        return "MARKET", 0
    
    if confidence >= 80:
        offset = 0.001
    elif confidence >= 70:
        offset = 0.002
    else:
        offset = 0.003
    
    if signal_type == "BUY":
        limit_price = mid_price * (1 - offset)
    else:
        limit_price = mid_price * (1 + offset)
    
    return "LIMIT", limit_price


def should_retry_execution(
    error_code: str,
    attempt: int,
    max_attempts: int = 3
) -> Tuple[bool, int]:
    retry_codes = {
        "INSUFFICIENT_BALANCE": False,
        "PRICE_SLIPPED": True,
        "TIMEOUT": True,
        "CONNECTION_ERROR": True,
        "RATE_LIMITED": True
    }
    
    should_retry = retry_codes.get(error_code, False)
    
    if not should_retry:
        return False, 0
    
    backoff_seconds = min(2 ** attempt, 30)
    
    return should_retry, backoff_seconds


def execute_with_Timeout(
    signal: Dict,
    executor_func,
    max_retries: int = 3
) -> Dict:
    result = None
    last_error = None
    
    for attempt in range(max_retries):
        try:
            result = executor_func(signal)
            return result
        except Exception as e:
            last_error = str(e)
            logger.warning(f">>> EXECUTE ATTEMPT {attempt + 1} FAILED: {e}")
            
            should_retry, backoff = should_retry_execution(
                error_code=last_error,
                attempt=attempt,
                max_attempts=max_retries
            )
            
            if not should_retry:
                break
            
            import time
            time.sleep(backoff)
    
    return {"success": False, "error": last_error, "attempts": max_retries}