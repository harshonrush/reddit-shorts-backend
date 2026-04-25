# redis_queue.py - Redis Queue configuration
import os
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


def safe_redis_get(key: str):
    """Safely get from Redis with error handling."""
    try:
        return redis_conn.get(key)
    except Exception as e:
        print(f"[REDIS ERROR] Failed to get {key}: {e}")
        return None


def safe_redis_set(key: str, value, ex=None):
    """Safely set to Redis with error handling."""
    try:
        return redis_conn.set(key, value, ex=ex)
    except Exception as e:
        print(f"[REDIS ERROR] Failed to set {key}: {e}")
        return False
