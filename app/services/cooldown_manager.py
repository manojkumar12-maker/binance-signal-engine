import time


class CooldownManager:
    def __init__(self):
        self.cache = {}
        self.cache_data = {}
        self.expiry = {}

    def build_fingerprint(self, signal):
        entry = round(signal.get("entry_primary", signal.get("entry", 0)), 2)
        return f"{signal['pair']}:{signal['signal']}:{entry}"

    def is_improved(self, new_signal, old_signal):
        if new_signal["signal"] != old_signal["signal"]:
            return True

        if new_signal["signal"] == "BUY":
            return new_signal.get("entry_primary", new_signal.get("entry", 0)) < old_signal.get("entry_primary", old_signal.get("entry", 0))

        if new_signal["signal"] == "SELL":
            return new_signal.get("entry_primary", new_signal.get("entry", 0)) > old_signal.get("entry_primary", old_signal.get("entry", 0))

        return False

    def get_cooldown(self, signal):
        base = 120
        confidence = signal.get("confidence", 50)
        return max(45, base - int(confidence))

    def is_blocked(self, signal):
        fp = self.build_fingerprint(signal)

        if fp not in self.cache:
            return False

        old_signal = self.cache_data.get(fp)

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

    def cleanup_expired(self):
        current_time = time.time()
        expired = [fp for fp, exp_time in self.expiry.items() if current_time >= exp_time]
        for fp in expired:
            self.cache.pop(fp, None)
            self.cache_data.pop(fp, None)
            self.expiry.pop(fp, None)


cooldown_manager = CooldownManager()
