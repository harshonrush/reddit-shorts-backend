import os
import tempfile
import re
import traceback
import requests
import uuid
import json
import time
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

# Validate environment variables on startup
from validate_env import validate_env
validate_env()

# RunPod configuration
RUNPOD_URL = os.getenv("RUNPOD_URL")
RUNPOD_API_KEY = os.getenv("RUNPOD_API_KEY")

from script_engine import generate_script
from tts import generate_audio
from video_fetcher import fetch_video
from subtitle_ass import generate_ass
from renderer import render_video
from uploader import upload_video
from auth_routes import router as auth_router
from scheduler import update_schedule, load_settings, save_settings, daily_job
from redis_queue import video_queue, redis_conn, safe_redis_get, safe_redis_set
from rq import Retry
from db import supabase

app = FastAPI(title="Reddit Reels API")

# Output directory for generated videos
OUTPUT_DIR = "/app/assets/output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Mount static files for serving videos
app.mount("/assets", StaticFiles(directory="/app/assets"), name="assets")

# Include auth routes
app.include_router(auth_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

OUTPUT_DIR = os.path.abspath(os.path.join("..", "assets", "output"))
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Redis Queue handles concurrency - no threading needed


class GenerateRequest(BaseModel):
    topic: str
    user_id: str = "default"


class UploadRequest(BaseModel):
    video_path: str
    title: str = "Crazy Reddit Story"
    description: str = "#shorts #reddit #story"


class ScriptRequest(BaseModel):
    idea: str
    user_id: str = "default"


class ScriptResponse(BaseModel):
    script: str
    script_id: str


class VideoJobRequest(BaseModel):
    script: str
    user_id: str = "default"


class VideoJobResponse(BaseModel):
    job_id: str
    status: str = "queued"


class JobStatusResponse(BaseModel):
    job_id: str
    status: str  # "queued" | "processing" | "completed" | "failed"
    video_url: str | None = None
    error: str | None = None


def safe_filename(text):
    return re.sub(r'[^a-zA-Z0-9_-]', '_', text)[:20]


def process_video_job(job_id: str, script: str, user_id: str):
    """RQ job: Process video generation via RunPod and update status."""
    try:
        # SAFE: Always create fresh object, never merge corrupted state
        job_data = {
            "status": "processing",
            "script": script,
            "user_id": user_id,
            "created_at": datetime.utcnow().isoformat()
        }
        safe_redis_set(job_id, json.dumps(job_data), ex=3600)

        # Step 1: Trigger RunPod job (async)
        print(f"[JOB {job_id}] Triggering RunPod job...")
        res = requests.post(
            RUNPOD_URL,
            headers={"Authorization": f"Bearer {RUNPOD_API_KEY}"},
            json={"input": {"topic": script[:100]}},
            timeout=60
        )

        result = res.json()
        print(f"[JOB {job_id}] RunPod trigger response: {result}")

        runpod_job_id = result.get("id")
        if not runpod_job_id:
            raise Exception(f"RunPod didn't return job id: {result}")

        # Step 2: Poll for completion (max 60 attempts = ~2 min)
        status_url = f"{RUNPOD_URL}/{runpod_job_id}"
        output = None

        for attempt in range(60):
            time.sleep(2)

            status_res = requests.get(
                status_url,
                headers={"Authorization": f"Bearer {RUNPOD_API_KEY}"},
                timeout=30
            )
            status_data = status_res.json()

            runpod_status = status_data.get("status")
            print(f"[JOB {job_id}] Poll {attempt+1}/60: {runpod_status}")

            if runpod_status == "COMPLETED":
                output = status_data.get("output", {})
                print(f"[JOB {job_id}] RunPod completed, output: {output}")
                break

            elif runpod_status in ["FAILED", "CANCELLED", "TIMED_OUT"]:
                raise Exception(f"RunPod job {runpod_status}: {status_data}")

        if not output:
            raise Exception("RunPod polling timeout")

        # Step 3: Process successful result (fresh object)
        if output.get("status") == "success":
            import base64
            video_base64 = output.get("video")
            if video_base64:
                video_bytes = base64.b64decode(video_base64)
                output_path = os.path.join(OUTPUT_DIR, user_id, f"video_{job_id}.mp4")
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                with open(output_path, "wb") as f:
                    f.write(video_bytes)

                # FRESH object - never merge
                job_data = {
                    "status": "completed",
                    "script": script,
                    "user_id": user_id,
                    "video_url": f"/assets/output/{user_id}/video_{job_id}.mp4",
                    "completed_at": datetime.utcnow().isoformat()
                }
                safe_redis_set(job_id, json.dumps(job_data), ex=3600)
                print(f"[JOB {job_id}] Video completed: {output_path}")
            else:
                raise Exception("No video data in RunPod output")
        else:
            raise Exception(f"RunPod handler failed: {output}")

    except Exception as e:
        print(f"[JOB {job_id}] Error: {e}")
        # FRESH object on error
        job_data = {
            "status": "failed",
            "script": script,
            "user_id": user_id,
            "error": str(e)[:200],
            "failed_at": datetime.utcnow().isoformat()
        }
        safe_redis_set(job_id, json.dumps(job_data), ex=3600)


@app.post("/generate-script", response_model=ScriptResponse)
async def generate_script_endpoint(request: ScriptRequest):
    """Step 1: Generate script from idea (cheap, fast, Railway handles)."""
    try:
        # Generate script using Gemini
        script = generate_script(request.idea)

        # Store script in Redis for 24h
        script_id = f"script:{uuid.uuid4().hex[:12]}"
        safe_redis_set(script_id, script, ex=86400)

        return ScriptResponse(script=script, script_id=script_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/generate-video", response_model=VideoJobResponse)
async def generate_video_job(request: VideoJobRequest):
    """Step 2: Queue video generation (expensive, async, RunPod GPU)."""
    # Rate limiting
    cooldown_key = f"cooldown:{request.user_id}"
    if safe_redis_get(cooldown_key):
        raise HTTPException(status_code=429, detail="Rate limit: Wait 60 seconds before next video")
    safe_redis_set(cooldown_key, 1, ex=60)

    try:
        # Create truly unique job ID with timestamp to avoid collisions
        job_id = f"job:{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"

        # Store job status
        job_data = {
            "status": "queued",
            "script": request.script,
            "user_id": request.user_id,
            "created_at": datetime.utcnow().isoformat()
        }
        safe_redis_set(job_id, json.dumps(job_data), ex=3600)

        # Enqueue job to RQ
        video_queue.enqueue(
            process_video_job,
            job_id,
            request.script,
            request.user_id,
            retry=Retry(max=3, interval=[10, 30, 60]),
            job_timeout=600
        )

        return VideoJobResponse(job_id=job_id, status="queued")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/job-status/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str):
    """Check video generation status."""
    try:
        # Get job data from Redis
        raw = safe_redis_get(job_id)
        if not raw:
            raise HTTPException(status_code=404, detail="Job not found")

        # SAFE: Handle corrupted JSON
        try:
            job_data = json.loads(raw)
        except json.JSONDecodeError as e:
            print(f"[REDIS CORRUPTION] raw value: {raw[:100]}...")
            return JobStatusResponse(
                job_id=job_id,
                status="failed",
                error="Corrupted job data"
            )

        return JobStatusResponse(
            job_id=job_id,
            status=job_data.get("status", "unknown"),
            video_url=job_data.get("video_url"),
            error=job_data.get("error")
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Legacy endpoint - keep for compatibility
@app.post("/generate")
async def generate_video_legacy(request: GenerateRequest):
    """Legacy: Direct RunPod call (kept for compatibility)."""
    cooldown_key = f"cooldown:{request.user_id}"
    if safe_redis_get(cooldown_key):
        raise HTTPException(status_code=429, detail="Rate limit: Wait 60 seconds")
    safe_redis_set(cooldown_key, 1, ex=60)

    try:
        res = requests.post(
            RUNPOD_URL,
            headers={"Authorization": f"Bearer {RUNPOD_API_KEY}"},
            json={"input": {"topic": request.topic}},
            timeout=60
        )
        return res.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/upload")
async def upload_to_youtube(request: UploadRequest):
    """Upload video to YouTube."""
    try:
        res = upload_video(
            file_path=request.video_path,
            title=request.title,
            description=request.description
        )
        return {"status": "uploaded", "youtube_id": res["id"], "url": f"https://youtube.com/watch?v={res['id']}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/upload-latest")
async def upload_latest(user_id: str = "default"):
    """Upload most recent generated video (for testing)."""
    try:
        user_dir = os.path.join(OUTPUT_DIR, user_id)

        if not os.path.exists(user_dir):
            raise HTTPException(status_code=404, detail="No videos for this user.")

        videos = [f for f in os.listdir(user_dir) if f.endswith(".mp4")]

        if not videos:
            raise HTTPException(status_code=404, detail="No videos found.")

        videos.sort(
            key=lambda x: os.path.getmtime(os.path.join(user_dir, x)),
            reverse=True
        )

        latest = os.path.join(user_dir, videos[0])

        res = upload_video(
            file_path=latest,
            title="Crazy Reddit Story",
            description="#shorts #reddit #storytime",
            tags=["reddit", "story", "shorts", "viral"]
        )

        return {
            "status": "uploaded",
            "youtube_id": res["id"],
            "url": f"https://youtube.com/watch?v={res['id']}"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.on_event("startup")
def on_startup():
    # No APScheduler - using external cron only
    pass


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


# Auto-post settings endpoints
@app.get("/settings/auto-post")
async def get_auto_post_settings(user_id: str = "default"):
    """Get current auto-post settings for a user."""
    return load_settings(user_id)


@app.post("/settings/auto-post")
async def set_auto_post_settings(enabled: bool, hour: int = 18, minute: int = 0, user_id: str = "default", niche: str = "stories"):
    """Update auto-post settings for a user."""
    update_schedule(enabled, hour, minute, user_id, niche)
    return {"status": "updated", "enabled": enabled, "time": f"{hour}:{minute:02d}", "user_id": user_id, "niche": niche}


# Trigger endpoint for external cron service
@app.post("/trigger-daily-post")
async def trigger_daily_post(user_id: str = "default", secret: str = None):
    """Trigger daily post manually (for cron-job.org or similar)."""
    # Optional: add secret check for security
    expected_secret = os.getenv("CRON_SECRET")
    if expected_secret and secret != expected_secret:
        raise HTTPException(status_code=401, detail="Invalid secret")
    
    # Check if enabled for this user
    settings = load_settings(user_id)
    if not settings.get("enabled", False):
        return {"status": "skipped", "reason": "Auto-post disabled for this user"}
    
    # Fetch token for this user
    token_res = supabase.table("user_tokens").select("*").eq("user_id", user_id).execute()
    if not token_res.data:
        return {"status": "skipped", "reason": "No YouTube token found"}
    token_data = token_res.data[0]
    
    # Enqueue to Redis worker
    video_queue.enqueue(
        daily_job,
        user_id,
        token_data,
        retry=Retry(max=3, interval=[10, 30, 60]),
        job_timeout=600
    )
    
    return {"status": "triggered", "user_id": user_id}


# Cron endpoint for cron-job.org (runs every 5 minutes)
@app.get("/cron/run")
def run_cron(secret: str):
    """Check all users and run daily job if scheduled time matches."""
    # Security check
    cron_secret = os.getenv("CRON_SECRET")
    if not secret or (cron_secret and secret != cron_secret):
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    from datetime import datetime, timedelta
    from scheduler import daily_job, load_settings, save_settings
    
    # Convert UTC to IST for comparison (user stores time in IST)
    try:
        import pytz
        ist = pytz.timezone("Asia/Kolkata")
        now = datetime.now(ist)
    except:
        # Fallback: manual IST calculation (UTC+5:30)
        now = datetime.utcnow() + timedelta(hours=5, minutes=30)
    
    print(f"[CRON HIT IST] {now.strftime('%H:%M')}")
    
    triggered = []
    today = now.strftime("%Y-%m-%d")
    
    # 🚀 Single JOIN query: users_settings + user_tokens, only enabled users
    res = supabase.table("users_settings") \
        .select("*,user_tokens(*)") \
        .eq("enabled", True) \
        .execute()
    
    for settings in res.data:
        user_id = settings["user_id"]
        
        if settings.get("is_posting"):
            continue
        
        if settings.get("last_posted_date") == today:
            continue
        
        # Check token exists from joined data (bulletproof handling)
        token_data = settings.get("user_tokens")

        # Case 1: None
        if not token_data:
            print(f"[CRON SKIP] {user_id} no token")
            continue

        # Case 2: list (Supabase returns relations as list)
        if isinstance(token_data, list):
            if len(token_data) == 0:
                print(f"[CRON SKIP] {user_id} empty token list")
                continue
            token_data = token_data[0]

        # Case 3: dict → already usable
        elif isinstance(token_data, dict):
            pass

        else:
            print(f"[CRON SKIP] {user_id} invalid token format")
            continue
        
        # 5-minute window match (cron runs every 5 min, check if within window)
        from datetime import timedelta
        scheduled_time = now.replace(
            hour=settings["hour"],
            minute=settings["minute"],
            second=0,
            microsecond=0
        )

        # If scheduled time is in future, check previous day
        if scheduled_time > now:
            scheduled_time -= timedelta(days=1)

        diff_seconds = (now - scheduled_time).total_seconds()

        if diff_seconds > 300:  # 5 minute window
            continue

        print(f"[CRON MATCH] {user_id} at {now.hour}:{now.minute:02d} (diff: {int(diff_seconds)}s)")

        # 🚨 ATOMIC LOCK: Set is_posting=True (last_posted_date set by worker on success)
        lock_res = supabase.table("users_settings") \
            .update({"is_posting": True}) \
            .eq("user_id", user_id) \
            .eq("is_posting", False) \
            .execute()
        
        # If no rows updated, lock failed (already posting)
        if not lock_res.data:
            print(f"[CRON SKIP] {user_id} lock failed (already posting)")
            continue

        print(f"[CRON RUNNING] {user_id} (lock acquired, enqueueing job)")
        
        # 🔥 REDIS LOCK: Prevent duplicate enqueuing (24h expiry)
        lock_key = f"lock:{user_id}:{today}"
        if safe_redis_get(lock_key):
            print(f"[CRON SKIP] {user_id} Redis lock exists (job already enqueued or running)")
            continue

        safe_redis_set(lock_key, 1, ex=86400)
        
        # 🚨 EXTRA SAFETY: Verify our lock is still active (is_posting should be True)
        fresh_check = supabase.table("users_settings").select("is_posting").eq("user_id", user_id).execute()
        if fresh_check.data:
            check = fresh_check.data[0]
            # If is_posting is not True, another process modified it (race condition)
            if not check.get("is_posting"):
                print(f"[CRON SKIP] {user_id} lock lost (race condition)")
                continue
        
        # Enqueue to Redis worker with retries (pass pre-fetched token)
        video_queue.enqueue(
            daily_job,
            user_id,
            token_data,
            retry=Retry(max=3, interval=[10, 30, 60]),
            job_timeout=600
        )
        
        triggered.append(user_id)
    
    return {"status": "checked", "triggered": triggered, "time": now.isoformat()}


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)