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

# Settings directory
SETTINGS_DIR = "settings"
os.makedirs(SETTINGS_DIR, exist_ok=True)


def get_settings_path(user_id: str):
    """Get settings file path for a user."""
    return os.path.join(SETTINGS_DIR, f"{user_id}.json")


def load_settings(user_id: str = "default"):
    """Load auto-post settings for a user."""
    import json
    settings_path = get_settings_path(user_id)
    if os.path.exists(settings_path):
        with open(settings_path, "r") as f:
            return json.load(f)
    return {"enabled": False, "hour": 18, "minute": 0}


def save_settings(settings, user_id: str = "default"):
    """Save auto-post settings for a user."""
    import json
    settings_path = get_settings_path(user_id)
    with open(settings_path, "w") as f:
        json.dump(settings, f)


def daily_job(user_id: str = "default"):
    """Generate and upload video daily."""
    settings = load_settings(user_id)
    if not settings.get("enabled", False):
        print(f"[SCHEDULER] Auto-post disabled for user {user_id}, skipping.")
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
        result = render_video(audio_path, video_path, ass_path, output_path, max_duration=60)
        
        if not result:
            print(f"[SCHEDULER] ❌ Render failed for user {user_id}")
            return
        
        # 7. Cleanup temp files
        for f in [audio_path, video_path, ass_path]:
            if os.path.exists(f):
                os.remove(f)
        
        # 8. Upload to YouTube
        print(f"[SCHEDULER] Uploading to YouTube for user {user_id}...")
        res = upload_video(
            file_path=output_path,
            title=f"Crazy {topic.title()} Story",
            description=f"#{topic.replace(' ', '')} #shorts #reddit #storytime",
            tags=["reddit", "story", "shorts", topic],
            user_id=user_id
        )
        
        print(f"[SCHEDULER] ✅ Posted: https://youtube.com/watch?v={res['id']}")
        
    except Exception as e:
        print(f"[SCHEDULER] ❌ Error: {e}")
        import traceback
        traceback.print_exc()


def start(user_id: str = "default"):
    """Start the scheduler with loaded settings."""
    settings = load_settings(user_id)
    
    if settings.get("enabled", False):
        trigger = CronTrigger(
            hour=settings.get("hour", 18),
            minute=settings.get("minute", 0)
        )
        job_id = f"daily_post_{user_id}"
        scheduler.add_job(daily_job, trigger, id=job_id, replace_existing=True, args=[user_id])
        scheduler.start()
        print(f"[SCHEDULER] Started for user {user_id} - daily at {settings.get('hour', 18)}:{settings.get('minute', 0):02d}")
    else:
        # Start scheduler but no jobs
        if not scheduler.running:
            scheduler.start()
        print(f"[SCHEDULER] Started for user {user_id} (auto-post disabled)")


def update_schedule(enabled: bool, hour: int = 18, minute: int = 0, user_id: str = "default"):
    """Update schedule settings for a user."""
    save_settings({"enabled": enabled, "hour": hour, "minute": minute}, user_id)
    
    job_id = f"daily_post_{user_id}"
    
    # Remove existing job
    try:
        scheduler.remove_job(job_id)
    except:
        pass
    
    if enabled:
        trigger = CronTrigger(hour=hour, minute=minute)
        scheduler.add_job(daily_job, trigger, id=job_id, replace_existing=True, args=[user_id])
        print(f"[SCHEDULER] Updated for user {user_id} - daily at {hour}:{minute:02d}")
    else:
        print(f"[SCHEDULER] Auto-post disabled for user {user_id}")
