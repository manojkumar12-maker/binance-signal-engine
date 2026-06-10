import time
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta
import config


class RiskEngine:
    def __init__(self):
        self.account_balance = 10000
        self.peak_balance = 10000
        self.daily_pnl = 0
        self.daily_start_balance = 10000
        self.max_drawdown = config.MAX_DRAWDOWN_PCT
        self.daily_loss_limit = config.DAILY_LOSS_LIMIT
        self.max_open_trades = config.MAX_OPEN_TRADES
        self.open_trades_count = 0
        self.last_reset_date = datetime.utcnow().date()
    
    def update_balance(self, new_balance: float):
        if new_balance > self.peak_balance:
            self.peak_balance = new_balance
        self.account_balance = new_balance
    
    def check_daily_reset(self):
        current_date = datetime.utcnow().date()
        if current_date > self.last_reset_date:
            self.daily_pnl = 0
            self.daily_start_balance = self.account_balance
            self.last_reset_date = current_date
    
    def get_current_drawdown(self) -> float:
        if self.peak_balance <= 0:
            return 0
        return (self.peak_balance - self.account_balance) / self.peak_balance
    
    def is_drawdown_safe(self) -> Tuple[bool, str]:
        dd = self.get_current_drawdown()
        if dd >= self.max_drawdown:
            return False, f"DRAWDOWN_LIMIT_REACHED ({round(dd*100,2)}%)"
        return True, "OK"
    
    def is_daily_loss_safe(self) -> Tuple[bool, str]:
        self.check_daily_reset()
        if self.daily_pnl <= 0:
            loss_pct = abs(self.daily_pnl) / self.daily_start_balance
            if loss_pct >= self.daily_loss_limit:
                return False, f"DAILY_LOSS_LIMIT_REACHED ({round(loss_pct*100,2)}%)"
        return True, "OK"
    
    def can_open_trade(self) -> Tuple[bool, str]:
        is_dd_safe, dd_reason = self.is_drawdown_safe()
        if not is_dd_safe:
            return False, dd_reason
        
        is_dl_safe, dl_reason = self.is_daily_loss_safe()
        if not is_dl_safe:
            return False, dl_reason
        
        if self.open_trades_count >= self.max_open_trades:
            return False, f"MAX_OPEN_TRADES_REACHED ({self.open_trades_count})"
        
        return True, "OK"
    
    def get_confidence_risk(self, confidence: float) -> float:
        if confidence >= 90:
            return config.HIGH_CONFIDENCE_RISK
        elif confidence >= 80:
            return config.MEDIUM_CONFIDENCE_RISK
        elif confidence >= 70:
            return config.NORMAL_RISK
        else:
            return config.LOW_CONFIDENCE_RISK
    
    def calculate_position_size(
        self,
        risk_pct: float,
        entry: float,
        stop_loss: float
    ) -> float:
        if entry <= 0 or stop_loss <= 0 or entry == stop_loss:
            return 0
        
        risk_amount = self.account_balance * risk_pct
        sl_distance = abs(entry - stop_loss) / entry
        
        if sl_distance == 0:
            return 0
        
        position_size = risk_amount / sl_distance
        return round(position_size, 4)
    
    def calculate_leverage(
        self,
        risk_pct: float,
        entry: float,
        stop_loss: float,
        max_leverage: int = 10
    ) -> int:
        if entry <= 0 or stop_loss <= 0 or entry == stop_loss:
            return 1
        
        sl_distance = abs(entry - stop_loss) / entry
        if sl_distance == 0:
            return 1
        
        leverage = risk_pct / sl_distance
        return min(int(leverage), max_leverage)
    
    def calculate_dynamic_sl(
        self,
        entry: float,
        candles: list,
        signal_type: str,
        atr_multiplier: float = None
    ) -> Tuple[float, float]:
        from app.services import volume
        
        if atr_multiplier is None:
            atr_multiplier = config.ATR_MULTIPLIER
        
        atr = volume.calculate_atr(candles)
        sl_distance = atr * atr_multiplier
        
        min_sl_distance = entry * 0.003
        if sl_distance < min_sl_distance:
            sl_distance = min_sl_distance
        
        if signal_type == "BUY":
            sl = entry - sl_distance
        else:
            sl = entry + sl_distance
        
        risk_pct = round(abs(entry - sl) / entry * 100, 2)
        return sl, risk_pct
    
    def calculate_tp_levels(
        self,
        entry: float,
        sl: float,
        signal_type: str,
        rr_multipliers: list = None
    ) -> Tuple[float, float, float]:
        if rr_multipliers is None:
            rr_multipliers = [1.5, 3.0]
        
        if signal_type == "BUY":
            risk = entry - sl
            tp1 = entry + risk * rr_multipliers[0]
            tp2 = entry + risk * rr_multipliers[1]
            tp3 = entry + risk * (rr_multipliers[1] * 1.5)
        else:
            risk = sl - entry
            tp1 = entry - risk * rr_multipliers[0]
            tp2 = entry - risk * rr_multipliers[1]
            tp3 = entry - risk * (rr_multipliers[1] * 1.5)
        
        return tp1, tp2, tp3
    
    def validate_rr(
        self,
        entry: float,
        sl: float,
        tp: float,
        signal_type: str,
        min_rr: float = 2.0
    ) -> Tuple[bool, float]:
        if entry <= 0 or sl <= 0 or tp <= 0:
            return False, 0
        
        if signal_type == "BUY":
            risk = entry - sl
            reward = tp - entry
        else:
            risk = sl - entry
            reward = entry - tp
        
        if risk <= 0:
            return False, 0
        
        rr = reward / risk
        return rr >= min_rr, round(rr, 2)
    
    def build_position(
        self,
        signal: Dict,
        candles: list
    ) -> Optional[Dict]:
        entry = signal.get("entry_primary", 0)
        confidence = signal.get("confidence", 0)
        signal_type = signal.get("signal", "BUY")
        
        if entry <= 0:
            return None
        
        can_trade, reason = self.can_open_trade()
        if not can_trade:
            return None
        
        sl, risk_pct = self.calculate_dynamic_sl(entry, candles, signal_type)
        
        tp1, tp2, tp3 = self.calculate_tp_levels(entry, sl, signal_type)
        
        is_rr_valid, rr = self.validate_rr(entry, sl, tp1, signal_type)
        if not is_rr_valid:
            return None
        
        risk = self.get_confidence_risk(confidence)
        
        position_size = self.calculate_position_size(risk, entry, sl)
        
        leverage = self.calculate_leverage(risk, entry, sl)
        
        self.open_trades_count += 1
        
        return {
            "entry": entry,
            "sl": sl,
            "tp1": tp1,
            "tp2": tp2,
            "tp3": tp3,
            "position_size": position_size,
            "leverage": leverage,
            "risk_pct": risk,
            "risk_amount": round(self.account_balance * risk, 2),
            "rr": rr,
            "confidence": confidence
        }
    
    def update_trade_pnl(self, pnl: float):
        self.daily_pnl += pnl
        self.account_balance += pnl
    
    def close_trade(self):
        if self.open_trades_count > 0:
            self.open_trades_count -= 1
    
    def get_dashboard(self) -> Dict:
        return {
            "balance": round(self.account_balance, 2),
            "peak_balance": round(self.peak_balance, 2),
            "drawdown_pct": round(self.get_current_drawdown() * 100, 2),
            "daily_pnl": round(self.daily_pnl, 2),
            "open_trades": self.open_trades_count,
            "max_trades": self.max_open_trades,
            "can_trade": self.can_open_trade()[0]
        }


risk_engine = RiskEngine()
