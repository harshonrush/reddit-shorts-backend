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
from scheduler import start as start_scheduler, update_schedule, load_settings

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
    start_scheduler()


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
    
    thread = threading.Thread(target=run_job)
    thread.start()
    
    return {"status": "triggered", "user_id": user_id}


# Cron endpoint for cron-job.org (runs every 5 minutes)
@app.get("/cron/run")
def run_cron(secret: str = None):
    """Check all users and run daily job if scheduled time matches."""
    # Security check
    cron_secret = os.getenv("CRON_SECRET")
    if cron_secret and secret != cron_secret:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    from datetime import datetime, timedelta
    from scheduler import daily_job, SETTINGS_DIR, load_settings, save_settings
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
    
    # Find all user settings files
    if os.path.exists(SETTINGS_DIR):
        for filename in os.listdir(SETTINGS_DIR):
            if filename.endswith(".json"):
                user_id = filename.replace(".json", "")
                settings = load_settings(user_id)
                
                if not settings.get("enabled", False):
                    continue
                
                # Get scheduled time (stored as IST)
                scheduled_hour = settings.get("hour", 18)
                scheduled_minute = settings.get("minute", 0)
                
                # Prevent duplicate posting
                today = now.strftime("%Y-%m-%d")
                if settings.get("last_posted_date") == today:
                    continue

                # Lock to prevent race condition
                if settings.get("is_posting"):
                    continue

                scheduled_time = now.replace(
                    hour=scheduled_hour,
                    minute=scheduled_minute,
                    second=0,
                    microsecond=0
                )

                if not (scheduled_time <= now <= scheduled_time + timedelta(minutes=2)):
                    continue

                print(f"[CRON RUNNING] {user_id}")

                # Set lock
                settings["is_posting"] = True
                save_settings(settings, user_id)

                def run_job(uid=user_id):
                    from scheduler import daily_job
                    try:
                        daily_job(uid)
                    finally:
                        # Release lock
                        s = load_settings(uid)
                        s["is_posting"] = False
                        save_settings(s, uid)

                thread = threading.Thread(target=run_job)
                thread.start()

                triggered.append(user_id)
    
    return {"status": "checked", "triggered": triggered, "time": now.isoformat()}


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)