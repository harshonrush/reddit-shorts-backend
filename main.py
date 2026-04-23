import os
import tempfile
import re
import traceback
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from script_engine import generate_story, generate_script
from tts import generate_audio
from video_fetcher import fetch_video
from subtitle_ass import generate_ass
from renderer import render_video
from uploader import upload_video
from auth_routes import router as auth_router
from scheduler import update_schedule, load_settings

app = FastAPI(title="Reddit Reels API")

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

import threading

MAX_THREADS = 5
active_threads = []

def run_limited_thread(target):
    global active_threads
    active_threads = [t for t in active_threads if t.is_alive()]
    if len(active_threads) >= MAX_THREADS:
        print("⚠️ Too many active jobs, skipping")
        return False
    t = threading.Thread(target=target)
    t.start()
    active_threads.append(t)
    return True


class GenerateRequest(BaseModel):
    topic: str
    user_id: str = "default"


class UploadRequest(BaseModel):
    video_path: str
    title: str = "Crazy Reddit Story"
    description: str = "#shorts #reddit #story"


def safe_filename(text):
    return re.sub(r'[^a-zA-Z0-9_-]', '_', text)[:20]


@app.post("/generate")
async def generate_video(request: GenerateRequest):
    audio_path = video_path = ass_path = None

    try:
        # 1. Story
        story = generate_story(request.topic)

        # 2. Script
        script = generate_script(story)
        script = " ".join(script.split()[:120])

        # 3. Audio
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            audio_path = f.name
        generate_audio(script, audio_path)

        # 4. Background video
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            video_path = f.name
        fetch_video(video_path)

        # 5. Subtitles
        with tempfile.NamedTemporaryFile(suffix=".ass", delete=False) as f:
            ass_path = f.name
        generate_ass(script, audio_path, ass_path)

        # 6. Per-user output
        user_output_dir = os.path.join(OUTPUT_DIR, request.user_id)
        os.makedirs(user_output_dir, exist_ok=True)

        filename = f"reel_{safe_filename(request.topic)}.mp4"
        output_path = os.path.join(user_output_dir, filename)

        # 7. Render
        render_video(audio_path, video_path, ass_path, output_path, max_duration=90)

        return FileResponse(output_path, media_type="video/mp4", filename=filename)

    except Exception as e:
        print(f"ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        for f in [audio_path, video_path, ass_path]:
            if f and os.path.exists(f):
                os.remove(f)


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
    
    # Run the job
    from scheduler import daily_job
    import threading
    
    def run_job():
        daily_job(user_id)
    
    if not run_limited_thread(run_job):
        return {"status": "skipped", "reason": "Too many active jobs"}
    
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
    from db import supabase
    import threading
    
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
    
    # Query all user settings from Supabase
    res = supabase.table("users_settings").select("*").execute()
    
    for settings in res.data:
        user_id = settings["user_id"]
        
        if not settings.get("enabled"):
            continue
        
        if settings.get("is_posting"):
            continue
        
        today = now.strftime("%Y-%m-%d")
        if settings.get("last_posted_date") == today:
            continue
        
        scheduled_time = now.replace(
            hour=settings["hour"],
            minute=settings["minute"],
            second=0,
            microsecond=0
        )

        diff_minutes = abs((now - scheduled_time).total_seconds()) / 60

        if diff_minutes > 10:
            continue

        # 🚨 RE-CHECK: Race condition protection
        # Query fresh data right before locking
        fresh = supabase.table("users_settings").select("is_posting,last_posted_date").eq("user_id", user_id).execute()
        if not fresh.data:
            continue
        user = fresh.data[0]

        if user.get("is_posting"):
            print(f"[CRON SKIP] {user_id} already posting (race condition caught)")
            continue

        if user.get("last_posted_date") == today:
            print(f"[CRON SKIP] {user_id} already posted today")
            continue

        print(f"[CRON RUNNING] {user_id}")

        # LOCK + MARK
        save_settings(user_id, {
            "is_posting": True
        })
        
        def run_job(uid=user_id, date_str=today):
            try:
                daily_job(uid)
                save_settings(uid, {
                    "is_posting": False,
                    "last_posted_date": date_str
                })
            except Exception as e:
                print(f"[CRON ERROR] {e}")
                save_settings(uid, {
                    "is_posting": False
                })
        
        if not run_limited_thread(run_job):
            # Unlock if we couldn't start the thread so it retries next cron tick
            save_settings(user_id, {"is_posting": False})
            continue
        
        triggered.append(user_id)
    
    return {"status": "checked", "triggered": triggered, "time": now.isoformat()}


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)