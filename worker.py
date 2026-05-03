# worker.py
import os
import redis
from rq import Worker, Queue

# Validate environment variables on startup
from validate_env import validate_env
validate_env()

# Import job functions so RQ can deserialize them
from scheduler import daily_job

redis_conn = redis.from_url(os.getenv("REDIS_URL"))

queue = Queue("video-jobs", connection=redis_conn)

if __name__ == "__main__":
    print("[WORKER] Starting worker with imported jobs...")
    print(f"[WORKER] Queue: video-jobs")
    print(f"[WORKER] Redis: {os.getenv('REDIS_URL', 'NOT SET')[:30]}...")
    print(f"[WORKER] Imported daily_job: {daily_job}")
    
    try:
        worker = Worker([queue], connection=redis_conn)
        print("[WORKER] Worker initialized, starting work loop...")
        worker.work()
    except Exception as e:
        print(f"[WORKER ERROR] {e}")
        import traceback
        traceback.print_exc()
        raise
