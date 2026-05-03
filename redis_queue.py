# redis_queue.py - Redis Queue configuration
import os
import json
import redis
from rq import Queue

REDIS_URL = os.getenv("REDIS_URL")

if not REDIS_URL:
    raise RuntimeError("❌ REDIS_URL not set. Worker cannot start.")

redis_conn = redis.from_url(REDIS_URL)
print("[REDIS] ✅ Connected")

video_queue = Queue(
    "video-jobs",
    connection=redis_conn,
    default_timeout=600
)


def safe_redis_set(key, value, ex=900):
    """Safely set to Redis - handles JSON serialization internally.
    
    Args:
        ex: Expiry time in seconds (default 900 = 15 min for backup safety)
    """
    if not isinstance(value, str):
        value = json.dumps(value)
    redis_conn.set(key, value, ex=ex)


def safe_redis_get(key):
    """Safely get from Redis - returns decoded string."""
    val = redis_conn.get(key)
    if val is None:
        return None
    if isinstance(val, bytes):
        val = val.decode("utf-8")
    return val
