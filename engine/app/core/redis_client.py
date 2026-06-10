import os
import json
import redis

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")

try:
    r = redis.from_url(REDIS_URL, decode_responses=True)
    r.ping()
    REDIS_AVAILABLE = True
except:
    r = None
    REDIS_AVAILABLE = False

MEMORY_CACHE = {}


def set_data(key: str, value, use_redis: bool = True):
    json_val = json.dumps(value)
    
    if use_redis and REDIS_AVAILABLE and r:
        try:
            r.set(key, json_val)
        except:
            MEMORY_CACHE[key] = value
    else:
        MEMORY_CACHE[key] = value


def get_data(key: str, use_redis: bool = True):
    if use_redis and REDIS_AVAILABLE and r:
        try:
            data = r.get(key)
            return json.loads(data) if data else None
        except:
            return MEMORY_CACHE.get(key)
    return MEMORY_CACHE.get(key)


def delete_data(key: str):
    if REDIS_AVAILABLE and r:
        try:
            r.delete(key)
        except:
            pass
    MEMORY_CACHE.pop(key, None)
