from typing import Dict, Tuple


def check_mtf_alignment(htf_trend: str, ltf_trend: str) -> Tuple[bool, str, float]:
    if htf_trend == "RANGE" or ltf_trend == "RANGE":
        return True, "ALIGNED", 0
    
    if htf_trend == ltf_trend:
        return True, "ALIGNED", 10
    
    if htf_trend == "UPTREND" and ltf_trend == "DOWNTREND":
        return False, "HTF_LTF_CONFLICT", -20
    elif htf_trend == "DOWNTREND" and ltf_trend == "UPTREND":
        return False, "HTF_LTF_CONFLICT", -20
    
    if htf_trend == "RANGE":
        return True, "HTF_RANGE_LTF_TREND", 0
    
    return True, "UNKNOWN", 0


def calculate_mtf_confidence_penalty(htf_trend: str, ltf_trend: str) -> float:
    is_aligned, alignment_type, penalty = check_mtf_alignment(htf_trend, ltf_trend)
    return penalty


def get_mtf_status(htf_trend: str, ltf_trend: str) -> Dict:
    is_aligned, alignment_type, bonus = check_mtf_alignment(htf_trend, ltf_trend)
    
    return {
        "is_aligned": is_aligned,
        "alignment_type": alignment_type,
        "confidence_adjustment": bonus,
        "htf_trend": htf_trend,
        "ltf_trend": ltf_trend,
        "recommendation": "EXECUTE" if is_aligned else "SKIP_OR_REDUCE"
    }


def enforce_mtf_rules(htf_candles: list, ltf_candles: list) -> Tuple[bool, Dict]:
    if not htf_candles or not ltf_candles:
        return True, {"status": "NO_DATA", "recommendation": "PROCEED"}
    
    from app.services import structure
    
    htf_trend = structure.detect_trend(htf_candles)
    ltf_trend = structure.detect_trend(ltf_candles)
    
    mtf_status = get_mtf_status(htf_trend, ltf_trend)
    
    if not mtf_status["is_aligned"]:
        mtf_status["recommendation"] = "SKIP"
    else:
        mtf_status["recommendation"] = "EXECUTE"
    
    return mtf_status["is_aligned"], mtf_status
