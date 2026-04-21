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


class UploadRequest(BaseModel):
    video_path: str
    title: str = "Crazy Reddit Story"
    description: str = "#shorts #reddit #story"


def safe_filename(text):
    return re.sub(r'[^a-zA-Z0-9_-]', '_', text)[:20]


@app.post("/generate")
async def generate_video(request: GenerateRequest):
    try:
        # 1. Story
        story = generate_story(request.topic)

        # 2. Script (IMPORTANT: trim length)
        script = generate_script(story)
        words = script.split()[:120]  # limit words
        script = " ".join(words)

        # 3. Audio
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            audio_path = f.name
        generate_audio(script, audio_path)

        # 4. Background video
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            video_path = f.name
        fetch_video(video_path)

        # 5. Subtitles (ASS format with audio-synced timing)
        with tempfile.NamedTemporaryFile(suffix=".ass", delete=False) as f:
            ass_path = f.name
        generate_ass(script, audio_path, ass_path)

        # 6. Output file
        filename = f"reel_{safe_filename(request.topic)}.mp4"
        output_path = os.path.join(OUTPUT_DIR, filename)

        # 7. Render (IMPORTANT: limit duration)
        render_video(audio_path, video_path, ass_path, output_path, max_duration=90)

        # 8. Cleanup
        for f in [audio_path, video_path, ass_path]:
            if os.path.exists(f):
                os.remove(f)

        # 9. Return video directly (BEST for now)
        return FileResponse(output_path, media_type="video/mp4", filename=filename)

    except Exception as e:
        print(f"ERROR: {e}")
        traceback.print_exc()
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
async def upload_latest():
    """Upload most recent generated video (for testing)."""
    try:
        # Find most recent video in output dir
        videos = [f for f in os.listdir(OUTPUT_DIR) if f.endswith('.mp4')]
        if not videos:
            raise HTTPException(status_code=404, detail="No videos found. Generate one first.")
        
        # Get most recent
        videos.sort(key=lambda x: os.path.getmtime(os.path.join(OUTPUT_DIR, x)), reverse=True)
        latest = os.path.join(OUTPUT_DIR, videos[0])
        
        res = upload_video(
            file_path=latest,
            title="Crazy Reddit Story",
            description="#shorts #reddit #storytime",
            tags=["reddit", "story", "shorts", "viral"]
        )
        return {"status": "uploaded", "youtube_id": res["id"], "url": f"https://youtube.com/watch?v={res['id']}"}
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
async def set_auto_post_settings(enabled: bool, hour: int = 18, minute: int = 0, user_id: str = "default"):
    """Update auto-post settings for a user."""
    update_schedule(enabled, hour, minute, user_id)
    return {"status": "updated", "enabled": enabled, "time": f"{hour}:{minute:02d}", "user_id": user_id}


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
def run_cron():
    """Check all users and run daily job if scheduled time matches."""
    from datetime import datetime
    from scheduler import daily_job, SETTINGS_DIR, load_settings
    import threading
    
    now = datetime.utcnow()  # Railway uses UTC
    print(f"[CRON HIT] {now.isoformat()}")
    
    triggered = []
    
    # Find all user settings files
    if os.path.exists(SETTINGS_DIR):
        for filename in os.listdir(SETTINGS_DIR):
            if filename.endswith(".json"):
                user_id = filename.replace(".json", "")
                settings = load_settings(user_id)
                
                if not settings.get("enabled", False):
                    continue
                
                # Get scheduled time (stored as UTC)
                scheduled_hour = settings.get("hour", 18)
                scheduled_minute = settings.get("minute", 0)
                
                # Check if current UTC time matches scheduled time (within 5-min window)
                if now.hour == scheduled_hour and abs(now.minute - scheduled_minute) < 5:
                    print(f"[CRON] Triggering for user {user_id} at {now.hour}:{now.minute:02d}")
                    
                    # Run in background thread
                    def run_job(uid=user_id):
                        daily_job(uid)
                    
                    thread = threading.Thread(target=run_job)
                    thread.start()
                    triggered.append(user_id)
    
    return {"status": "checked", "triggered": triggered, "time": now.isoformat()}


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)