import time


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


class CooldownManager:
    def __init__(self):
        self.cache = {}
        self.cache_data = {}
        self.expiry = {}
        self.recent_pairs = set()

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
        self.recent_pairs.add(signal["pair"])

    def cleanup_expired(self):
        current_time = time.time()
        expired = [fp for fp, exp_time in self.expiry.items() if current_time >= exp_time]
        for fp in expired:
            pair = fp.split(":")[0]
            self.recent_pairs.discard(pair)
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


cooldown_manager = CooldownManager()
