import time
import config
from typing import Dict, List, Tuple


PERFORMANCE_WINDOW_TRADES = 50
PERFORMANCE_WINDOW_HOURS = 24


class PerformanceTracker:
    def __init__(self):
        self.trade_history = []
        self.wins = 0
        self.losses = 0
        self.total_pnl = 0
        self.win_rate = 0.5
        self.avg_win = 0
        self.avg_loss = 0
        self.current_streak = 0
        self.best_streak = 0
        self.worst_streak = 0
        
    def add_trade(self, pnl_pct: float, trade_data: Dict = None):
        self.trade_history.append({
            "pnl": pnl_pct,
            "timestamp": time.time(),
            "data": trade_data or {}
        })
        
        if len(self.trade_history) > PERFORMANCE_WINDOW_TRADES * 2:
            self.trade_history = self.trade_history[-(PERFORMANCE_WINDOW_TRADES * 2):]
        
        self._recalculate()
    
    def _recalculate(self):
        if not self.trade_history:
            return
            
        closed_trades = [t for t in self.trade_history if "pnl" in t]
        
        self.wins = sum(1 for t in closed_trades if t["pnl"] > 0)
        self.losses = sum(1 for t in closed_trades if t["pnl"] <= 0)
        
        total = self.wins + self.losses
        if total > 0:
            self.win_rate = self.wins / total
        
        wins_list = [t["pnl"] for t in closed_trades if t["pnl"] > 0]
        losses_list = [t["pnl"] for t in closed_trades if t["pnl"] <= 0]
        
        self.avg_win = sum(wins_list) / len(wins_list) if wins_list else 0
        self.avg_loss = abs(sum(losses_list) / len(losses_list)) if losses_list else 0
        
        self.total_pnl = sum(t["pnl"] for t in closed_trades)
        
        streak = 0
        for t in reversed(closed_trades):
            if t["pnl"] > 0:
                streak += 1
            else:
                break
        self.current_streak = streak
        
        best = 0
        current = 0
        for t in closed_trades:
            if t["pnl"] > 0:
                current += 1
                best = max(best, current)
            else:
                current = 0
        self.best_streak = best
    
    def get_recent_win_rate(self, last_n: int = 20) -> float:
        if not self.trade_history:
            return 0.5
        
        recent = self.trade_history[-last_n:]
        wins = sum(1 for t in recent if t["pnl"] > 0)
        return wins / len(recent) if recent else 0.5
    
    def get_adaptive_confidence_threshold(self, base_threshold: float = 70) -> float:
        recent_wr = self.get_recent_win_rate()
        
        if recent_wr < 0.35:
            return min(base_threshold + 15, 90)
        elif recent_wr < 0.45:
            return min(base_threshold + 10, 85)
        elif recent_wr > 0.65:
            return max(base_threshold - 10, 50)
        elif recent_wr > 0.55:
            return max(base_threshold - 5, 60)
        
        return base_threshold
    
    def get_adaptive_risk(self, base_risk: float = 0.01) -> float:
        recent_wr = self.get_recent_win_rate()
        
        if recent_wr < 0.35:
            return base_risk * 0.5
        elif recent_wr < 0.45:
            return base_risk * 0.75
        elif recent_wr > 0.65:
            return base_risk * 1.5
        elif recent_wr > 0.55:
            return base_risk * 1.25
        
        return base_risk
    
    def should_pause_trading(self) -> Tuple[bool, str]:
        recent_wr = self.get_recent_win_rate()
        
        if recent_wr < 0.25:
            return True, f"EXTREME_DROUGHT (win rate: {recent_wr*100:.1f}%)"
        
        if self.current_streak >= 8 and recent_wr < 0.4:
            return True, f"LOSS_STREAK ({self.current_streak} losses)"
        
        return False, "OK"
    
    def get_stats(self) -> Dict:
        return {
            "win_rate": round(self.win_rate * 100, 2),
            "recent_win_rate": round(self.get_recent_win_rate() * 100, 2),
            "wins": self.wins,
            "losses": self.losses,
            "total_pnl": round(self.total_pnl, 2),
            "avg_win": round(self.avg_win, 2),
            "avg_loss": round(self.avg_loss, 2),
            "current_streak": self.current_streak,
            "total_trades": len(self.trade_history)
        }


performance_tracker = PerformanceTracker()
