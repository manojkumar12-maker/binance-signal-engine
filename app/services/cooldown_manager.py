import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class CooldownManager:
    def __init__(self):
        self.SNIPER_MODE = False
        self.cooldowns = {}
        self.signal_history = []
        self.max_history = 100
    
    def filter_diversity(self, signals: list, max_per_pair: int = 1) -> list:
        if not signals:
            return []
        
        filtered = []
        pairs_seen = set()
        
        for signal in signals:
            pair = signal.get("pair")
            if pair not in pairs_seen:
                filtered.append(signal)
                pairs_seen.add(pair)
                if len(pairs_seen) >= max_per_pair * 3:
                    break
        
        return filtered
    
    def process_signals(self, signals: list) -> list:
        if not signals:
            return []
        
        now = datetime.utcnow()
        processed = []
        
        for signal in signals:
            pair = signal.get("pair")
            signal_type = signal.get("signal")
            key = f"{pair}_{signal_type}"
            
            if key in self.cooldowns:
                if now - self.cooldowns[key] < timedelta(minutes=30):
                    continue
            
            processed.append(signal)
            self.cooldowns[key] = now
            
            self.signal_history.append({
                "pair": pair,
                "signal": signal_type,
                "timestamp": now,
                "confidence": signal.get("confidence", 0)
            })
        
        if len(self.signal_history) > self.max_history:
            self.signal_history = self.signal_history[-self.max_history:]
        
        return processed
    
    def cleanup_expired(self):
        now = datetime.utcnow()
        expired = []
        
        for key, timestamp in self.cooldowns.items():
            if now - timestamp > timedelta(hours=1):
                expired.append(key)
        
        for key in expired:
            del self.cooldowns[key]

cooldown_manager = CooldownManager()