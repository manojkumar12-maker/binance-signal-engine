import logging

logger = logging.getLogger(__name__)

_cache = {}

def set_cache(key: str, value: any, ttl: int = 60):
    _cache[key] = {"value": value, "expires": __import__("time").time() + ttl}
    logger.info(f"[CACHE] Set: {key}")

def get_cache(key: str) -> any:
    if key in _cache:
        if _cache[key]["expires"] > __import__("time").time():
            return _cache[key]["value"]
        else:
            del _cache[key]
    return None

def clear_cache():
    global _cache
    _cache = {}
    logger.info("[CACHE] Cleared")