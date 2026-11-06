import os
import sys

# Ensure src is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.config import settings


def main():
    settings.fail_closed_if_inconsistent()
    print(f"Binance Signal Engine starting in mode={settings.trading_mode} live_authorized={settings.live_authorized}")
    if settings.paper_mode:
        print("PAPER mode: no real orders will be placed.")
    if os.getenv("RUN_WORKER", "true").lower() in ("1", "true", "yes"):
        import threading
        from src.worker import main as worker_main
        t = threading.Thread(target=worker_main, daemon=True)
        t.start()
        print("Worker thread started.")
    import uvicorn
    uvicorn.run("src.dashboard:app", host=settings.host, port=settings.port, log_level=settings.log_level.lower())


if __name__ == "__main__":
    main()