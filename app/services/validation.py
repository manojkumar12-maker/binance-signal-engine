from typing import Dict, Optional
from datetime import datetime


def validate_signal(signal: Dict) -> tuple[bool, Optional[str]]:
    if not signal:
        return False, "No signal data"

    if signal.get("signal") == "NO TRADE":
        return False, "No trade signal"

    trend = signal.get("trend", "")
    if "RANGE" in trend and "REVERSAL" not in trend:
        return False, "RANGE trend (no clear direction)"

    entry = signal.get("entry_primary", 0)
    if entry <= 0:
        return False, "Invalid entry price"

    sl = signal.get("sl", 0)
    if sl <= 0:
        return False, "Invalid stop loss"

    risk_pct = signal.get("risk_pct", 0)
    if risk_pct <= 0:
        return False, "Invalid risk (0 or negative)"

    if risk_pct > 3.0:
        return False, f"Risk too high ({risk_pct}%)"

    confidence = signal.get("confidence", 0)
    if confidence < 30:
        return False, f"Very low confidence ({confidence}) - applying penalty instead of reject"
    
    if confidence > 95:
        return False, f"Unrealistic confidence ({confidence})"

    atr_ratio = signal.get("atr_ratio", 0)
    if atr_ratio < 0.0003:
        return False, "Very low volatility (flat market)"

    return True, None


def classify_signal_type(signal: Dict) -> str:
    if signal.get("is_reversal", False):
        return "REVERSAL"

    if signal.get("fake_breakout", False):
        return "REVERSAL"

    return "CONTINUATION"


def apply_regime_adjustments(signal: Dict, regime: str, regime_config: dict) -> Dict:
    confidence = signal.get("confidence", 50)

    confidence += regime_config.get("continuation_bonus", 0)

    signal["regime"] = regime
    signal["regime_min_confidence"] = regime_config.get("min_confidence", 65)

    if regime == "LOW_VOL":
        signal["signal"] = "NO TRADE"
        signal["reason"] = "LOW_VOL regime - no trade"
        return signal

    if confidence < regime_config.get("min_confidence", 60):
        signal["signal"] = "NO TRADE"
        signal["reason"] = f"Confidence below regime minimum ({regime})"
        return signal

    signal["confidence"] = max(0, min(100, confidence))

    return signal
