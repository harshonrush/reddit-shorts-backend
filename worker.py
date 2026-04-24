# worker.py
import os
import redis
from rq import Worker, Queue

redis_conn = redis.from_url(os.getenv("REDIS_URL"))

queue = Queue("video-jobs", connection=redis_conn)

if __name__ == "__main__":
    worker = Worker([queue], connection=redis_conn)
    worker.work()
