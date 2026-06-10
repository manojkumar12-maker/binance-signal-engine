from typing import Dict, Tuple
import config


def check_sniper_conditions(
    confidence: float,
    entry_score: float,
    whale_alignment: str,
    liquidity_confirmed: str,
    extension_filter: bool,
    mtf_aligned: bool
) -> Tuple[bool, Dict]:
    checks = {}
    all_passed = True
    
    if liquidity_confirmed is None:
        liquidity_confirmed = "NEUTRAL"
    
    checks["confidence_check"] = {
        "passed": confidence >= config.SNIPER_MODE_CONFIDENCE,
        "value": confidence,
        "threshold": config.SNIPER_MODE_CONFIDENCE,
        "description": f"Confidence >= {config.SNIPER_MODE_CONFIDENCE}%"
    }
    
    if not checks["confidence_check"]["passed"]:
        all_passed = False
    
    checks["entry_score_check"] = {
        "passed": entry_score >= config.SNIPER_MODE_ENTRY_SCORE,
        "value": entry_score,
        "threshold": config.SNIPER_MODE_ENTRY_SCORE,
        "description": f"Entry Quality >= {config.SNIPER_MODE_ENTRY_SCORE}"
    }
    
    if not checks["entry_score_check"]["passed"]:
        all_passed = False
    
    if config.SNIPER_MODE_WHALE_ALIGNMENT:
        checks["whale_alignment_check"] = {
            "passed": whale_alignment in ["ACCUMULATION", "DISTRIBUTION"],
            "value": whale_alignment,
            "description": "Whale aligned (ACCUMULATION/DISTRIBUTION)"
        }
        
        if not checks["whale_alignment_check"]["passed"]:
            all_passed = False
    
    if config.SNIPER_MODE_LIQUIDITY_CONFIRMED:
        checks["liquidity_check"] = {
            "passed": liquidity_confirmed in ["SWEEP_LOW_REJECTION", "SWEEP_HIGH_REJECTION"],
            "value": liquidity_confirmed,
            "description": "Liquidity sweep confirmed"
        }
        
        if not checks["liquidity_check"]["passed"]:
            all_passed = False
    
    checks["extension_check"] = {
        "passed": not extension_filter,
        "value": "EXTENDED" if extension_filter else "OK",
        "description": "Not overextended from EMA"
    }
    
    if not checks["extension_check"]["passed"]:
        all_passed = False
    
    checks["mtf_check"] = {
        "passed": mtf_aligned,
        "value": "ALIGNED" if mtf_aligned else "CONFLICT",
        "description": "Multi-timeframe alignment"
    }
    
    if not checks["mtf_check"]["passed"]:
        all_passed = False
    
    return all_passed, checks


def calculate_sniper_score(
    confidence: float,
    entry_score: float,
    whale_alignment: str,
    liquidity_confirmed: str,
    extension_filter: bool,
    mtf_aligned: bool
) -> float:
    if liquidity_confirmed is None:
        liquidity_confirmed = "NEUTRAL"
    
    score = 0
    
    score += (confidence / 100) * 30
    
    score += (entry_score / 100) * 25
    
    if whale_alignment in ["ACCUMULATION", "DISTRIBUTION"]:
        score += 15
    elif whale_alignment in ["SHORT_SQUEEZE", "LONG_LIQUIDATION"]:
        score += 5
    
    if liquidity_confirmed in ["SWEEP_LOW_REJECTION", "SWEEP_HIGH_REJECTION"]:
        score += 15
    
    if not extension_filter:
        score += 10
    
    if mtf_aligned:
        score += 5
    
    return min(100, score)


def is_sniper_trade(
    signal_data: Dict,
    cooldown_manager
) -> Tuple[bool, str]:
    confidence = signal_data.get("confidence", 0)
    entry_score = signal_data.get("entry_score", 0)
    whale_signal = signal_data.get("whale_signal", "NEUTRAL")
    liquidity = signal_data.get("liquidity") or "NEUTRAL"
    is_extended = signal_data.get("is_extended", False)
    mtf_aligned = signal_data.get("mtf_aligned", True)
    
    is_sniper, checks = check_sniper_conditions(
        confidence=confidence,
        entry_score=entry_score,
        whale_alignment=whale_signal,
        liquidity_confirmed=liquidity,
        extension_filter=is_extended,
        mtf_aligned=mtf_aligned
    )
    
    if is_sniper:
        return True, "SNIPER_TRADE"
    
    failed_checks = [k for k, v in checks.items() if not v["passed"]]
    return False, f"FAILED: {', '.join(failed_checks)}"


def get_sniper_eligibility(signal_data: Dict) -> Dict:
    confidence = signal_data.get("confidence", 0)
    entry_score = signal_data.get("entry_score", 0)
    whale_signal = signal_data.get("whale_signal", "NEUTRAL")
    liquidity = signal_data.get("liquidity") or "NEUTRAL"
    is_extended = signal_data.get("is_extended", False)
    mtf_aligned = signal_data.get("mtf_aligned", True)
    
    sniper_score = calculate_sniper_score(
        confidence=confidence,
        entry_score=entry_score,
        whale_alignment=whale_signal,
        liquidity_confirmed=liquidity,
        extension_filter=is_extended,
        mtf_aligned=mtf_aligned
    )
    
    is_sniper, reason = is_sniper_trade(signal_data, None)
    
    return {
        "sniper_score": round(sniper_score, 2),
        "is_sniper_eligible": is_sniper,
        "reason": reason,
        "confidence": confidence,
        "entry_score": entry_score,
        "whale_alignment": whale_signal,
        "liquidity_confirmed": liquidity,
        "extended": is_extended,
        "mtf_aligned": mtf_aligned
    }
