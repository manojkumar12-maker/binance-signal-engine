from typing import List, Dict
import structure


def detect_trend_strength(candles: List[Dict]) -> float:
    return structure.detect_trend_strength(candles)


def detect_market_regime(atr_ratio: float, trend: str, trend_strength: float = 0.0) -> str:
    if atr_ratio < 0.0008:
        return "LOW_VOL"
    
    if atr_ratio > 0.015:
        return "HIGH_VOL"
    
    if trend_strength > 0.6 and trend != "RANGE":
        return "TRENDING"
    
    if trend == "RANGE":
        return "RANGE"
    
    return "TRANSITION"


def get_regime_config(regime: str) -> dict:
    configs = {
        "TRENDING": {
            "min_confidence": 60,
            "continuation_bonus": 10,
            "max_risk_pct": 2.5,
            "allow_reversal": True,
        },
        "RANGE": {
            "min_confidence": 75,
            "continuation_bonus": -15,
            "max_risk_pct": 2.0,
            "allow_reversal": True,
        },
        "LOW_VOL": {
            "min_confidence": 80,
            "continuation_bonus": 0,
            "max_risk_pct": 1.5,
            "allow_reversal": False,
        },
        "HIGH_VOL": {
            "min_confidence": 70,
            "continuation_bonus": 5,
            "max_risk_pct": 3.0,
            "allow_reversal": True,
        },
        "TRANSITION": {
            "min_confidence": 70,
            "continuation_bonus": -5,
            "max_risk_pct": 2.0,
            "allow_reversal": True,
        },
    }
    return configs.get(regime, configs["TRANSITION"])
