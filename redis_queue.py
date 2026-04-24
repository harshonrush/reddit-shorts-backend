# redis_queue.py - Redis Queue configuration
import os
import redis
from rq import Queue

redis_url = os.getenv("REDIS_URL")

redis_conn = redis.from_url(redis_url)

video_queue = Queue(
    "video-jobs",
    connection=redis_conn,
    default_timeout=600
)
