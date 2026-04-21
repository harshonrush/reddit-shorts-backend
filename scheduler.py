"""Auto-posting scheduler for daily video generation and upload."""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import random
import os

scheduler = BackgroundScheduler()

# Viral topics pool
TOPICS = [
    "heartbreak",
    "cheating",
    "toxic parents",
    "revenge",
    "betrayal",
    "friendship gone wrong",
    "workplace drama",
    "family secrets"
]

# Settings file path
SETTINGS_FILE = "auto_post_settings.json"


def load_settings():
    """Load auto-post settings."""
    import json
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r") as f:
            return json.load(f)
    return {"enabled": False, "hour": 18, "minute": 0}


def save_settings(settings):
    """Save auto-post settings."""
    import json
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f)


def daily_job():
    """Generate and upload video daily."""
    settings = load_settings()
    if not settings.get("enabled", False):
        print("[SCHEDULER] Auto-post is disabled, skipping.")
        return
    
    # Pick random topic
    topic = random.choice(TOPICS)
    print(f"[SCHEDULER] Generating video for topic: {topic}")
    
    try:
        # Import here to avoid circular imports
        from script_engine import generate_story, generate_script
        from tts import generate_audio
        from video_fetcher import fetch_video
        from subtitle_ass import generate_ass
        from renderer import render_video
        from uploader import upload_video
        import tempfile
        
        OUTPUT_DIR = os.path.abspath(os.path.join("..", "assets", "output"))
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        
        # 1. Story
        story = generate_story(topic)
        
        # 2. Script
        script = generate_script(story)
        words = script.split()[:120]
        script = " ".join(words)
        
        # 3. Audio
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            audio_path = f.name
        generate_audio(script, audio_path)
        
        # 4. Video
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            video_path = f.name
        fetch_video(video_path)
        
        # 5. Subtitles
        with tempfile.NamedTemporaryFile(suffix=".ass", delete=False) as f:
            ass_path = f.name
        generate_ass(script, audio_path, ass_path)
        
        # 6. Render
        filename = f"auto_reel_{topic.replace(' ', '_')}.mp4"
        output_path = os.path.join(OUTPUT_DIR, filename)
        render_video(audio_path, video_path, ass_path, output_path, max_duration=90)
        
        # 7. Cleanup temp files
        for f in [audio_path, video_path, ass_path]:
            if os.path.exists(f):
                os.remove(f)
        
        # 8. Upload to YouTube
        print(f"[SCHEDULER] Uploading to YouTube...")
        res = upload_video(
            file_path=output_path,
            title=f"Crazy {topic.title()} Story",
            description=f"#{topic.replace(' ', '')} #shorts #reddit #storytime",
            tags=["reddit", "story", "shorts", topic]
        )
        
        print(f"[SCHEDULER] ✅ Posted: https://youtube.com/watch?v={res['id']}")
        
    except Exception as e:
        print(f"[SCHEDULER] ❌ Error: {e}")
        import traceback
        traceback.print_exc()


def start():
    """Start the scheduler with loaded settings."""
    settings = load_settings()
    
    if settings.get("enabled", False):
        trigger = CronTrigger(
            hour=settings.get("hour", 18),
            minute=settings.get("minute", 0)
        )
        scheduler.add_job(daily_job, trigger, id="daily_post", replace_existing=True)
        scheduler.start()
        print(f"[SCHEDULER] Started - daily at {settings.get('hour', 18)}:{settings.get('minute', 0):02d}")
    else:
        # Start scheduler but no jobs
        scheduler.start()
        print("[SCHEDULER] Started (auto-post disabled)")


def update_schedule(enabled: bool, hour: int = 18, minute: int = 0):
    """Update schedule settings."""
    save_settings({"enabled": enabled, "hour": hour, "minute": minute})
    
    # Remove existing job
    try:
        scheduler.remove_job("daily_post")
    except:
        pass
    
    if enabled:
        trigger = CronTrigger(hour=hour, minute=minute)
        scheduler.add_job(daily_job, trigger, id="daily_post", replace_existing=True)
        print(f"[SCHEDULER] Updated - daily at {hour}:{minute:02d}")
    else:
        print("[SCHEDULER] Auto-post disabled")
