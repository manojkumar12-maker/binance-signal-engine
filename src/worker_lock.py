"""Process-level worker lock.

Uses an OS advisory lock on POSIX (Render/Linux) so a live owner always keeps
exclusive ownership. The file descriptor stays open for the worker lifetime.
"""
import os
import atexit

LOCK_FILE = "data/worker.lock"

try:
    import fcntl
    _HAS_FCNTL = True
except Exception:
    _HAS_FCNTL = False


class WorkerLock:
    def __init__(self, path: str = LOCK_FILE):
        self.path = path
        self._fd = None
        self._acquired = False
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    def acquire(self, stale_seconds: int = 300) -> bool:
        if _HAS_FCNTL:
            return self._acquire_posix()
        return self._acquire_fallback()

    def _acquire_posix(self):
        import fcntl
        try:
            fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o644)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, OSError):
            try:
                os.close(fd)
            except Exception:
                pass
            return False
        try:
            os.ftruncate(fd, 0)
            os.write(fd, f"{os.getpid()}\n".encode())
            os.fsync(fd)
        except Exception:
            pass
        self._fd = fd
        self._acquired = True
        atexit.register(self.release)
        return True

    def _acquire_fallback(self):
        if os.path.exists(self.path):
            try:
                with open(self.path) as f:
                    pid = int(f.read().strip().split()[0])
                try:
                    os.kill(pid, 0)
                    return False
                except (OSError, ProcessLookupError, PermissionError):
                    pass
            except Exception:
                pass
            try:
                os.remove(self.path)
            except Exception:
                pass
        try:
            with open(self.path, "w") as f:
                f.write(f"{os.getpid()}\n")
            self._acquired = True
            atexit.register(self.release)
            return True
        except Exception:
            return False

    def release(self):
        if not self._acquired:
            return
        if _HAS_FCNTL and self._fd is not None:
            try:
                import fcntl
                fcntl.flock(self._fd, fcntl.LOCK_UN)
            except Exception:
                pass
            try:
                os.close(self._fd)
            except Exception:
                pass
            self._fd = None
        self._acquired = False

    def __del__(self):
        self.release()