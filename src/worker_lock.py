"""File-based worker lock to prevent overlapping cycles."""
import os
import time
import atexit

LOCK_FILE = "data/worker.lock"


class WorkerLock:
    def __init__(self, path: str = LOCK_FILE):
        self.path = path
        self._acquired = False
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    def acquire(self, stale_seconds: int = 300) -> bool:
        if os.path.exists(self.path):
            try:
                with open(self.path) as f:
                    pid, ts = f.read().split(",")
                ts = float(ts)
                if time.time() - ts < stale_seconds:
                    return False
            except Exception:
                pass
        try:
            with open(self.path, "w") as f:
                f.write(f"{os.getpid()},{time.time()}")
            self._acquired = True
            atexit.register(self.release)
            return True
        except Exception:
            return False

    def release(self):
        if self._acquired and os.path.exists(self.path):
            try:
                os.remove(self.path)
            except Exception:
                pass
        self._acquired = False