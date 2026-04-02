import time
from datetime import datetime


def normalize_price(price):
    if price > 1:
        return round(price, 2)
    return round(price, 4)


def is_same_signal(new_signal, old_signal):
    if not old_signal:
        return False
    
    new_entry = new_signal.get("entry_primary", 0)
    old_entry = old_signal.get("entry_primary", 0)
    
    if old_entry == 0:
        return False
    
    diff = abs(new_entry - old_entry) / old_entry
    return diff < 0.002


def is_on_cooldown(pair, new_signal, cache):
    if pair not in cache:
        return False

    old = cache[pair]
    
    if time.time() - old.get("timestamp", 0) > 180:
        cache.pop(pair, None)
        return False
    
    new_conf = new_signal.get("confidence", 0)
    old_conf = old.get("confidence", 0)
    
    if new_conf > old_conf + 15:
        cache.pop(pair, None)
        return False
    
    new_entry = new_signal.get("entry_primary", 0)
    old_entry = old.get("entry_primary", 0)
    if old_entry > 0 and abs(new_entry - old_entry) / old_entry > 0.005:
        cache.pop(pair, None)
        return False

    return True


def is_price_changed(pair, new_entry, cache):
    if pair not in cache:
        return True
    
    old_entry = cache[pair].get("entry_primary", 0)
    if old_entry == 0:
        return True
    
    change = abs(new_entry - old_entry) / old_entry
    return change > 0.005


def balance_signals(signals):
    buys = [s for s in signals if s.get("signal") == "BUY"]
    sells = [s for s in signals if s.get("signal") == "SELL"]
    
    if len(sells) > len(buys) * 2:
        sells = sorted(sells, key=lambda x: x.get("confidence", 0), reverse=True)[:3]
    
    if len(buys) > len(sells) * 2:
        buys = sorted(buys, key=lambda x: x.get("confidence", 0), reverse=True)[:3]
    
    return buys + sells


def filter_elite(signals, threshold=70):
    return [s for s in signals if s.get("confidence", 0) >= threshold]


def sniper_filter(signal):
    score = signal.get("confidence", 0)
    
    if score >= 85:
        return True
    
    if score >= 75:
        whale = signal.get("whale_signal")
        liquidity = signal.get("liquidity", "")
        if whale and whale != "NEUTRAL":
            return True
        if "REJECTION" in liquidity:
            return True
    
    return False


def fallback_filter(signals, threshold=65):
    return [s for s in signals if s.get("confidence", 0) >= threshold]


class CooldownManager:
    def __init__(self):
        self.cache = {}
        self.cache_data = {}
        self.expiry = {}
        self.signal_history = {}
        self.SNIPER_MODE = False

    def build_fingerprint(self, signal):
        entry = normalize_price(signal.get("entry_primary", 0))
        return f"{signal['pair']}:{signal['signal']}:{entry}"

    def is_improved(self, new_signal, old_signal):
        if new_signal["signal"] != old_signal["signal"]:
            return True

        if new_signal["signal"] == "BUY":
            return new_signal.get("entry_primary", 0) < old_signal.get("entry_primary", 0)

        if new_signal["signal"] == "SELL":
            return new_signal.get("entry_primary", 0) > old_signal.get("entry_primary", 0)

        return False

    def get_cooldown(self, signal):
        confidence = signal.get("confidence", 50)
        
        if confidence > 85:
            return 45
        if confidence > 70:
            return 90
        return 180

    def is_blocked(self, signal):
        fp = self.build_fingerprint(signal)

        if fp not in self.cache:
            return False

        old_signal = self.cache_data.get(fp)
        
        if is_same_signal(signal, old_signal):
            return True

        if old_signal and self.is_improved(signal, old_signal):
            return False

        if time.time() < self.expiry.get(fp, 0):
            return True

        return False

    def store(self, signal):
        fp = self.build_fingerprint(signal)
        cooldown = self.get_cooldown(signal)

        self.cache[fp] = True
        self.cache_data[fp] = signal
        self.expiry[fp] = time.time() + cooldown
        self.signal_history[signal["pair"]] = {
            "confidence": signal.get("confidence", 0),
            "entry_primary": signal.get("entry_primary", 0),
            "timestamp": time.time()
        }

    def cleanup_expired(self):
        current_time = time.time()
        expired = [fp for fp, exp_time in self.expiry.items() if current_time >= exp_time]
        for fp in expired:
            pair = fp.split(":")[0]
            self.cache.pop(fp, None)
            self.cache_data.pop(fp, None)
            self.expiry.pop(fp, None)

    def filter_diversity(self, signals, max_per_pair=1):
        seen_counts = {}
        used_bases = set()
        filtered = []
        
        for s in signals:
            pair = s["pair"]
            base = pair.replace("USDT", "").replace("BUSD", "")[:3]
            
            pair_count = seen_counts.get(pair, 0)
            if pair_count >= max_per_pair:
                continue
            
            if base in used_bases:
                continue
            
            filtered.append(s)
            seen_counts[pair] = pair_count + 1
            used_bases.add(base)
            
            if len(filtered) >= 5:
                break
        
        return filtered

    def process_signals(self, signals):
        if self.SNIPER_MODE:
            sniper_signals = [s for s in signals if sniper_filter(s)]
            sniper_signals = sorted(sniper_signals, key=lambda x: x.get("confidence", 0), reverse=True)[:3]
            if len(sniper_signals) > 0:
                for s in sniper_signals:
                    self.store(s)
                return sniper_signals
        
        filtered = filter_elite(signals, 70)
        
        filtered = balance_signals(filtered)
        
        filtered = sorted(filtered, key=lambda x: x.get("confidence", 0), reverse=True)[:10]
        
        if len(filtered) == 0 and len(signals) > 0:
            filtered = fallback_filter(signals, 65)
            filtered = sorted(filtered, key=lambda x: x.get("confidence", 0), reverse=True)[:5]
        
        for s in filtered:
            self.store(s)
        
        return filtered


cooldown_manager = CooldownManager()
