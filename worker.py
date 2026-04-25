# worker.py
import os
import redis
from rq import Worker, Queue

# Import job functions so RQ can deserialize them
from scheduler import daily_job

redis_conn = redis.from_url(os.getenv("REDIS_URL"))

queue = Queue("video-jobs", connection=redis_conn)

if __name__ == "__main__":
    print("[WORKER] Starting worker with imported jobs...")
    worker = Worker([queue], connection=redis_conn)
    worker.work()
