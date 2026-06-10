import os
import json
import redis

REDIS_URL = os.environ.get("REDIS_URL", "")

try:
    if REDIS_URL:
        r = redis.from_url(REDIS_URL, decode_responses=True)
        r.ping()
        REDIS_AVAILABLE = True
    else:
        r = None
        REDIS_AVAILABLE = False
except:
    r = None
    REDIS_AVAILABLE = False

MEMORY_CACHE = {}


def set_cache(key: str, value, ttl: int = 60):
    json_val = json.dumps(value)
    
    if REDIS_AVAILABLE and r:
        try:
            r.setex(key, ttl, json_val)
        except:
            MEMORY_CACHE[key] = value
    else:
        MEMORY_CACHE[key] = value


def get_cache(key: str):
    if REDIS_AVAILABLE and r:
        try:
            data = r.get(key)
            return json.loads(data) if data else None
        except:
            return MEMORY_CACHE.get(key)
    return MEMORY_CACHE.get(key)


def delete_cache(key: str):
    if REDIS_AVAILABLE and r:
        try:
            r.delete(key)
        except:
            pass
    MEMORY_CACHE.pop(key, None)
