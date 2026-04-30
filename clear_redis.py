"""Clear all job keys from Redis"""
import os
import redis

REDIS_URL = os.getenv("REDIS_URL")
if not REDIS_URL:
    print("❌ REDIS_URL not set")
    exit(1)

r = redis.from_url(REDIS_URL)

# Delete all job keys
for key in r.scan_iter(match="job:*"):
    print(f"Deleting {key}")
    r.delete(key)

# Also delete script keys
for key in r.scan_iter(match="script:*"):
    print(f"Deleting {key}")
    r.delete(key)

print("✅ Cleared all job and script keys")
