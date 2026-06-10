import time
import logging
from typing import Dict, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


SYSTEM_STATE = {
    "running": True,
    "paused_reason": None,
    "paused_at": None,
    "halted": False,
    "halt_reason": None,
    "auto_resume_enabled": True
}


def get_system_state() -> Dict:
    return {
        "running": SYSTEM_STATE["running"],
        "paused": not SYSTEM_STATE["running"],
        "paused_reason": SYSTEM_STATE["paused_reason"],
        "halted": SYSTEM_STATE["halted"],
        "halt_reason": SYSTEM_STATE["halt_reason"],
        "auto_resume": SYSTEM_STATE["auto_resume_enabled"]
    }


def is_trading_allowed() -> Tuple[bool, str]:
    if SYSTEM_STATE["halted"]:
        return False, f"SYSTEM_HALTED ({SYSTEM_STATE['halt_reason']})"
    
    if not SYSTEM_STATE["running"]:
        return False, f"PAUSED ({SYSTEM_STATE['paused_reason']})"
    
    return True, "OK"


def pause_trading(reason: str = "MANUAL") -> bool:
    if not SYSTEM_STATE["running"]:
        return False
    
    SYSTEM_STATE["running"] = False
    SYSTEM_STATE["paused_reason"] = reason
    SYSTEM_STATE["paused_at"] = time.time()
    
    logger.warning(f"Trading PAUSED: {reason}")
    return True


def resume_trading() -> bool:
    if not SYSTEM_STATE["paused_reason"]:
        return False
    
    SYSTEM_STATE["running"] = True
    SYSTEM_STATE["paused_reason"] = None
    SYSTEM_STATE["paused_at"] = None
    
    logger.info("Trading RESUMED")
    return True


def halt_system(reason: str, auto_resume: bool = False) -> bool:
    SYSTEM_STATE["running"] = False
    SYSTEM_STATE["halted"] = True
    SYSTEM_STATE["halt_reason"] = reason
    SYSTEM_STATE["auto_resume_enabled"] = auto_resume
    
    logger.critical(f"🚨 SYSTEM HALTED: {reason}")
    return True


def resume_from_halt() -> bool:
    SYSTEM_STATE["running"] = True
    SYSTEM_STATE["halted"] = False
    SYSTEM_STATE["halt_reason"] = None
    
    logger.info("System resumed from HALT state")
    return True


def check_drawdown_halt(drawdown_pct: float, threshold: float = 0.07) -> bool:
    if drawdown_pct >= threshold:
        halt_system(f"DRAWDOWN_LIMIT ({drawdown_pct*100:.1f}%)", auto_resume=True)
        return True
    return False


def check_daily_loss_halt(daily_loss_pct: float, threshold: float = 0.05) -> bool:
    if daily_loss_pct >= threshold:
        halt_system(f"DAILY_LOSS_LIMIT ({daily_loss_pct*100:.1f}%)", auto_resume=False)
        return True
    return False


def check_consecutive_losses_halt(losses: int, threshold: int = 8) -> bool:
    if losses >= threshold:
        halt_system(f"LOSS_STREAK ({losses} consecutive)", auto_resume=True)
        return True
    return False


def check_error_rate_halt(errors: int, total: int, threshold: float = 0.5) -> bool:
    if total > 10:
        error_rate = errors / total
        if error_rate >= threshold:
            halt_system(f"HIGH_ERROR_RATE ({error_rate*100:.1f}%)", auto_resume=True)
            return True
    return False


def auto_resume_if_allowed() -> bool:
    if not SYSTEM_STATE["halted"]:
        return False
    
    if not SYSTEM_STATE["auto_resume_enabled"]:
        return False
    
    paused_at = SYSTEM_STATE.get("paused_at", time.time())
    min_pause_time = 3600
    
    if time.time() - paused_at >= min_pause_time:
        logger.info("Auto-resuming system after cooldown period")
        return resume_from_halt()
    
    return False
