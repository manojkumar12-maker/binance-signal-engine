from typing import List, Dict, Tuple, Optional
from datetime import datetime, timedelta
import json
import logging
import config
from collections import defaultdict

logger = logging.getLogger("self_learning")

TRADE_HISTORY_FILE = "trade_history.json"
ADAPTIVE_WEIGHTS_FILE = "adaptive_weights.json"

feature_performance = defaultdict(lambda: {"wins": 0, "losses": 0, "total_pnl": 0.0})
feature_weights = {
    "liquidity": 20,
    "bos": 15,
    "choch": 20,
    "fvg": 5,
    "volume": 15,
    "whale": 15,
    "htf_aligned": 10,
    "vwap_aligned": 5,
    "reversal_strong": 20,
    "microstructure": 10,
    "absorption": 10,
    "delta_imbalance": 8
}

session_performance = defaultdict(lambda: {"wins": 0, "losses": 0})
optimal_sessions = ["LONDON", "NY"]
session_weights = {"LONDON": 1.0, "NY": 1.0, "ASIA": 0.7, "OTHER": 0.5}

regime_performance = defaultdict(lambda: {"wins": 0, "losses": 0})
regime_weights = {"TRENDING": 1.0, "RANGE": 0.8, "TRANSITION": 0.7, "LOW_VOL": 0.3}


def record_trade_outcome(
    features: Dict,
    trade_result: str,
    pnl_pct: float,
    session: str,
    regime: str
):
    global feature_performance, session_performance, regime_performance
    
    if trade_result not in ["WIN", "LOSS"]:
        return
    
    result_value = 1 if trade_result == "WIN" else -1
    
    for feature, active in features.items():
        if not active:
            continue
        if feature not in feature_performance:
            feature_performance[feature] = {"wins": 0, "losses": 0, "total_pnl": 0.0}
        
        if trade_result == "WIN":
            feature_performance[feature]["wins"] += 1
        else:
            feature_performance[feature]["losses"] += 1
        
        feature_performance[feature]["total_pnl"] += pnl_pct
    
    session_performance[session]["wins" if trade_result == "WIN" else "losses"] += 1
    regime_performance[regime]["wins" if trade_result == "WIN" else "losses"] += 1
    
    logger.info(f">>> LEARNED: {trade_result} | PnL: {pnl_pct:.2f}% | Features: {[k for k,v in features.items() if v]}")
    
    _save_performance_data()


def _save_performance_data():
    try:
        data = {
            "feature_performance": dict(feature_performance),
            "session_performance": dict(session_performance),
            "regime_performance": dict(regime_performance),
            "updated_at": datetime.utcnow().isoformat()
        }
        
        with open(ADAPTIVE_WEIGHTS_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.warning(f">>> SAVE WARNING: {e}")


def load_performance_data():
    try:
        with open(ADAPTIVE_WEIGHTS_FILE, 'r') as f:
            data = json.load(f)
            
            global feature_performance, session_performance, regime_performance
            
            fp = data.get("feature_performance", {})
            for k, v in fp.items():
                feature_performance[k] = v
            
            sp = data.get("session_performance", {})
            for k, v in sp.items():
                session_performance[k] = v
            
            rp = data.get("regime_performance", {})
            for k, v in rp.items():
                regime_performance[k] = v
            
            logger.info(f">>> LOADED: {len(feature_performance)} features tracked")
    except:
        pass


def get_adaptive_weight(feature: str, base_weight: int = 10) -> int:
    if feature not in feature_performance:
        return base_weight
    
    stats = feature_performance[feature]
    total = stats["wins"] + stats["losses"]
    
    if total < 5:
        return base_weight
    
    win_rate = stats["wins"] / total
    avg_pnl = stats["total_pnl"] / total
    
    if win_rate > 0.6 and avg_pnl > 0:
        return base_weight + 5
    elif win_rate > 0.55 and avg_pnl > 0:
        return base_weight + 3
    elif win_rate > 0.5:
        return base_weight + 1
    elif win_rate > 0.4:
        return base_weight - 1
    else:
        return max(3, base_weight - 3)


def get_session_bonus(session: str) -> int:
    base = session_weights.get(session, 0.5)
    
    if session not in session_performance:
        return int(base * 10)
    
    stats = session_performance[session]
    total = stats["wins"] + stats["losses"]
    
    if total < 3:
        return int(base * 10)
    
    win_rate = stats["wins"] / total
    
    if win_rate > 0.6:
        return 10
    elif win_rate > 0.5:
        return 5
    elif win_rate > 0.4:
        return 0
    else:
        return -5


def get_regime_bonus(regime: str) -> int:
    base = regime_weights.get(regime, 0.5)
    
    if regime not in regime_performance:
        return int(base * 10)
    
    stats = regime_performance[regime]
    total = stats["wins"] + stats["losses"]
    
    if total < 3:
        return int(base * 10)
    
    win_rate = stats["wins"] / total
    
    if win_rate > 0.6:
        return 10
    elif win_rate > 0.5:
        return 5
    elif win_rate > 0.4:
        return 0
    else:
        return -5


def get_performance_summary() -> Dict:
    summary = {
        "features": {},
        "sessions": {},
        "regimes": {},
        "total_trades": 0,
        "overall_win_rate": 0
    }
    
    total_wins = sum(s["wins"] for s in feature_performance.values())
    total_losses = sum(s["losses"] for s in feature_performance.values())
    summary["total_trades"] = total_wins + total_losses
    
    if summary["total_trades"] > 0:
        summary["overall_win_rate"] = round(total_wins / summary["total_trades"] * 100, 1)
    
    for feature, stats in feature_performance.items():
        total = stats["wins"] + stats["losses"]
        if total > 0:
            win_rate = stats["wins"] / total
            summary["features"][feature] = {
                "wins": stats["wins"],
                "losses": stats["losses"],
                "win_rate": round(win_rate * 100, 1),
                "avg_pnl": round(stats["total_pnl"] / total, 2) if total > 0 else 0,
                "adaptive_weight": get_adaptive_weight(feature, feature_weights.get(feature, 10))
            }
    
    for session, stats in session_performance.items():
        total = stats["wins"] + stats["losses"]
        if total > 0:
            summary["sessions"][session] = {
                "wins": stats["wins"],
                "losses": stats["losses"],
                "win_rate": round(stats["wins"] / total * 100, 1),
                "bonus": get_session_bonus(session)
            }
    
    for regime, stats in regime_performance.items():
        total = stats["wins"] + stats["losses"]
        if total > 0:
            summary["regimes"][regime] = {
                "wins": stats["wins"],
                "losses": stats["losses"],
                "win_rate": round(stats["wins"] / total * 100, 1),
                "bonus": get_regime_bonus(regime)
            }
    
    return summary


def get_confidence_adjustment(
    features: Dict,
    session: str,
    regime: str,
    base_confidence: int
) -> int:
    adjustments = 0
    
    for feature, active in features.items():
        if active:
            adjustments += get_adaptive_weight(feature, feature_weights.get(feature, 10)) - feature_weights.get(feature, 10)
    
    adjustments += get_session_bonus(session)
    adjustments += get_regime_bonus(regime)
    
    return max(-15, min(15, adjustments))


def detect_regime_shift() -> Tuple[bool, str]:
    try:
        from app.services import market
        btc_1h = market.get_klines("BTCUSDT", "1h", 50)
        
        if not btc_1h or len(btc_1h) < 20:
            return False, "NO_DATA"
        
        from app.services import volume
        atr = volume.calculate_atr(btc_1h, 14)
        current_price = btc_1h[-1]["close"]
        atr_ratio = atr / current_price if current_price > 0 else 0
        
        if atr_ratio > 0.01:
            return True, "HIGH_VOL"
        elif atr_ratio < 0.003:
            return True, "LOW_VOL"
        elif 0.003 <= atr_ratio <= 0.006:
            return True, "NORMAL"
        
        return False, "STABLE"
    except:
        return False, "ERROR"


def suggest_parameter_adjustments() -> Dict:
    summary = get_performance_summary()
    
    suggestions = {}
    
    for feature, data in summary.get("features", {}).items():
        if data["win_rate"] < 40 and data["total"] > 10:
            suggestions[feature] = {
                "action": "DECREASE",
                "reason": f"Low win rate: {data['win_rate']}%",
                "current_weight": feature_weights.get(feature, 10),
                "suggested_weight": max(3, feature_weights.get(feature, 10) - 3)
            }
        elif data["win_rate"] > 60 and data["total"] > 10:
            suggestions[feature] = {
                "action": "INCREASE",
                "reason": f"High win rate: {data['win_rate']}%",
                "current_weight": feature_weights.get(feature, 10),
                "suggested_weight": feature_weights.get(feature, 10) + 3
            }
    
    return suggestions


load_performance_data()