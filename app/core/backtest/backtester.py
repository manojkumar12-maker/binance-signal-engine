"""
PHASE 10: BACKTESTING FRAMEWORK
==============================

PURPOSE:
Backtest signal performance with institutional metrics.

METRICS:
- Win Rate: % of winning trades
- Profit Factor: Gross profit / Gross loss
- Max Drawdown: Largest peak-to-trough decline
- Sharpe Ratio: Risk-adjusted return
- Expectancy: Average expected return per trade
- Average R:R: Risk-to-reward ratio

USAGE:
1. Load historical signals
2. Simulate trades
3. Calculate metrics
4. Generate report

OUTPUT:
- Performance report dict
- Recommendations
"""

import numpy as np
from typing import Dict, List, Tuple
from dataclasses import dataclass
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class Trade:
    pair: str
    direction: str  # BUY or SELL
    entry: float
    sl: float
    tp1: float
    tp2: float
    tp3: float
    confidence: float
    entry_time: datetime
    exit_time: datetime = None
    exit_price: float = 0
    pnl: float = 0
    status: str = "OPEN"


class Backtester:
    """
    Institutional backtesting engine.
    """
    
    def __init__(self, initial_capital: float = 10000):
        self.initial_capital = initial_capital
        self.trades = []
        self.equity_curve = []
    
    def add_trade(self, trade: Trade):
        """Add completed trade to history."""
        self.trades.append(trade)
    
    def simulate(self, signals: List[Dict], price_data: Dict[str, List[float]]) -> Dict:
        """
        Simulate trades from signals.
        
        Args:
            signals: List of signal dicts with entry, sl, tp, etc.
            price_data: Dict of pair -> list of prices after signal
        
        Returns:
            Performance report dict
        """
        for signal in signals:
            pair = signal["pair"]
            direction = signal["signal"]
            entry = signal["entry"]
            sl = signal["sl"]
            tp1 = signal["tp1"]
            tp2 = signal["tp2"]
            tp3 = signal["tp3"]
            
            if pair not in price_data:
                continue
            
            prices = price_data[pair]
            
            # Simulate trade
            trade = self._simulate_trade(
                pair, direction, entry, sl, tp1, tp2, tp3, prices
            )
            self.add_trade(trade)
        
        return self.generate_report()
    
    def _simulate_trade(self, pair: str, direction: str, entry: float,
                        sl: float, tp1: float, tp2: float, tp3: float,
                        prices: List[float]) -> Trade:
        """Simulate single trade outcome."""
        
        trade = Trade(
            pair=pair,
            direction=direction,
            entry=entry,
            sl=sl,
            tp1=tp1,
            tp2=tp2,
            tp3=tp3,
            confidence=0,
            entry_time=datetime.now()
        )
        
        for price in prices:
            if direction == "BUY":
                if price <= sl:
                    trade.exit_price = sl
                    trade.pnl = (sl - entry) / entry
                    trade.status = "SL"
                    break
                elif price >= tp3:
                    trade.exit_price = tp3
                    trade.pnl = (tp3 - entry) / entry
                    trade.status = "TP3"
                    break
                elif price >= tp2:
                    trade.exit_price = tp2
                    trade.pnl = (tp2 - entry) / entry
                    trade.status = "TP2"
                    break
                elif price >= tp1:
                    trade.exit_price = tp1
                    trade.pnl = (tp1 - entry) / entry
                    trade.status = "TP1"
                    break
            
            else:  # SELL
                if price >= sl:
                    trade.exit_price = sl
                    trade.pnl = (entry - sl) / entry
                    trade.status = "SL"
                    break
                elif price <= tp3:
                    trade.exit_price = tp3
                    trade.pnl = (entry - tp3) / entry
                    trade.status = "TP3"
                    break
                elif price <= tp2:
                    trade.exit_price = tp2
                    trade.pnl = (entry - tp2) / entry
                    trade.status = "TP2"
                    break
                elif price <= tp1:
                    trade.exit_price = tp1
                    trade.pnl = (entry - tp1) / entry
                    trade.status = "TP1"
                    break
        
        if trade.status == "OPEN":
            # Trade didn't close - use last price
            trade.exit_price = prices[-1]
            if direction == "BUY":
                trade.pnl = (trade.exit_price - entry) / entry
            else:
                trade.pnl = (entry - trade.exit_price) / entry
            trade.status = "OPEN"
        
        trade.exit_time = datetime.now()
        return trade
    
    def generate_report(self) -> Dict:
        """Generate comprehensive performance report."""
        
        if not self.trades:
            return {"error": "No trades to analyze"}
        
        # Basic metrics
        total_trades = len(self.trades)
        wins = [t for t in self.trades if t.pnl > 0]
        losses = [t for t in self.trades if t.pnl <= 0]
        
        win_count = len(wins)
        loss_count = len(losses)
        
        win_rate = win_count / total_trades if total_trades > 0 else 0
        
        # PnL metrics
        gross_profit = sum(t.pnl for t in wins)
        gross_loss = abs(sum(t.pnl for t in losses))
        
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        # Average metrics
        avg_win = np.mean([t.pnl for t in wins]) if wins else 0
        avg_loss = np.mean([t.pnl for t in losses]) if losses else 0
        
        # R:R ratio
        avg_rr = abs(avg_win / avg_loss) if avg_loss != 0 else 0
        
        # Expectancy
        expectancy = (win_rate * avg_win) - ((1 - win_rate) * abs(avg_loss))
        
        # Drawdown
        equity = [self.initial_capital]
        for trade in self.trades:
            equity.append(equity[-1] * (1 + trade.pnl))
        
        max_dd = self._calculate_max_drawdown(equity)
        
        # Sharpe ratio (simplified)
        returns = [t.pnl for t in self.trades]
        if len(returns) > 1:
            sharpe = np.mean(returns) / np.std(returns) if np.std(returns) > 0 else 0
        else:
            sharpe = 0
        
        # Tier analysis
        tier_thresholds = {
            "SNIPER": 90,
            "ELITE": 80,
            "STANDARD": 75,
            "WATCH": 60
        }
        
        tier_performance = {}
        for tier, threshold in tier_thresholds.items():
            tier_trades = [t for t in self.trades if t.confidence >= threshold]
            if tier_trades:
                tier_wins = [t for t in tier_trades if t.pnl > 0]
                tier_win_rate = len(tier_wins) / len(tier_trades)
                tier_performance[tier] = {
                    "trades": len(tier_trades),
                    "win_rate": round(tier_win_rate * 100, 2),
                    "avg_pnl": round(np.mean([t.pnl for t in tier_trades]), 4)
                }
        
        # Recommendations
        recommendations = []
        if win_rate < 0.5:
            recommendations.append("Win rate below 50% - tighten filters")
        if profit_factor < 1.5:
            recommendations.append("Profit factor below 1.5 - review R:R")
        if max_dd > 0.20:
            recommendations.append("Max drawdown > 20% - reduce position size")
        if sharpe < 1.0:
            recommendations.append("Sharpe ratio below 1.0 - improve signal quality")
        
        return {
            "summary": {
                "total_trades": total_trades,
                "win_count": win_count,
                "loss_count": loss_count,
                "win_rate": round(win_rate * 100, 2),
                "profit_factor": round(profit_factor, 2),
                "max_drawdown": round(max_dd * 100, 2),
                "sharpe_ratio": round(sharpe, 2),
                "expectancy": round(expectancy, 4),
                "avg_rr": round(avg_rr, 2),
                "avg_win": round(avg_win, 4),
                "avg_loss": round(avg_loss, 4),
                "gross_profit": round(gross_profit, 4),
                "gross_loss": round(gross_loss, 4),
                "final_equity": round(equity[-1], 2),
                "return_pct": round((equity[-1] - self.initial_capital) / self.initial_capital * 100, 2)
            },
            "tier_performance": tier_performance,
            "recommendations": recommendations,
            "trades": [
                {
                    "pair": t.pair,
                    "direction": t.direction,
                    "entry": t.entry,
                    "exit": t.exit_price,
                    "pnl": round(t.pnl, 4),
                    "status": t.status,
                    "confidence": t.confidence
                }
                for t in self.trades
            ]
        }
    
    def _calculate_max_drawdown(self, equity: List[float]) -> float:
        """Calculate maximum drawdown from equity curve."""
        peak = equity[0]
        max_dd = 0
        
        for value in equity:
            if value > peak:
                peak = value
            
            dd = (peak - value) / peak
            if dd > max_dd:
                max_dd = dd
        
        return max_dd


# Global instance
_backtester = None

def get_backtester() -> Backtester:
    global _backtester
    if _backtester is None:
        _backtester = Backtester()
    return _backtester


def run_backtest(signals: List[Dict], price_data: Dict[str, List[float]]) -> Dict:
    backtester = get_backtester()
    return backtester.simulate(signals, price_data)