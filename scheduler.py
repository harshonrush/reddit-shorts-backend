"""Auto-posting scheduler for daily video generation and upload."""
import random
import os
import json
import logging
import time

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Niche-based topic mapping
NICHE_TOPICS = {
    "heartbreak": ["heartbreak", "breakup recovery", "moving on", "lost love", "emotional healing"],
    "motivation": ["discipline", "morning routine", "success mindset", "never give up", "transformation"],
    "business": ["startup struggle", "entrepreneur journey", "side hustle success", "business betrayal", "rags to riches"],
    "fitness": ["gym discipline", "weight loss journey", "fitness transformation", "mental strength", "health wake-up call"],
    "stories": ["creepy encounter", "strange neighbor", "mystery solved", "unexpected twist", "life changing moment"]
}

# Default random topics for backward compatibility
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
    return {"enabled": False, "hour": 18, "minute": 0, "niche": "stories"}


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
    
    # Pick topic based on user's niche
    niche = settings.get("niche", "stories")
    if niche in NICHE_TOPICS:
        topic = random.choice(NICHE_TOPICS[niche])
    else:
        topic = random.choice(TOPICS)
    print(f"[SCHEDULER] Niche: {niche} | Topic: {topic}")
    
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
        
        # 6. Render (per-user folder)
        user_output_dir = os.path.join(OUTPUT_DIR, user_id)
        os.makedirs(user_output_dir, exist_ok=True)
        filename = f"auto_reel_{topic.replace(' ', '_')}.mp4"
        output_path = os.path.join(user_output_dir, filename)
        result = render_video(audio_path, video_path, ass_path, output_path, max_duration=60)
        
        if not result:
            print(f"[SCHEDULER] ❌ Render failed for user {user_id}")
            return
        
        # 7. Cleanup temp files
        for f in [audio_path, video_path, ass_path]:
            if os.path.exists(f):
                os.remove(f)
        
        # 8. Upload to YouTube (with retry)
        logger.info(f"Uploading to YouTube for user {user_id}...")
        res = None
        for attempt in range(3):
            try:
                res = upload_video(
                    file_path=output_path,
                    title=f"Crazy {topic.title()} Story",
                    description=f"#{topic.replace(' ', '')} #shorts #reddit #storytime",
                    tags=["reddit", "story", "shorts", topic],
                    user_id=user_id
                )
                break
            except Exception as e:
                logger.error(f"Upload attempt {attempt + 1} failed: {e}")
                if attempt == 2:  # Last attempt
                    raise e
                time.sleep(5)  # Wait 5s before retry
        
        logger.info(f"Posted: https://youtube.com/watch?v={res['id']}")
        
    except Exception as e:
        logger.error(f"Error in daily_job for {user_id}: {e}")
        import traceback
        logger.error(traceback.format_exc())


def update_schedule(enabled: bool, hour: int = 18, minute: int = 0, user_id: str = "default", niche: str = None):
    """Update schedule settings for a user."""
    # Load existing settings to preserve fields like last_posted_date, is_posting
    settings = load_settings(user_id)
    
    # Update only the provided fields
    settings["enabled"] = enabled
    settings["hour"] = hour
    settings["minute"] = minute
    if niche:
        settings["niche"] = niche
    
    save_settings(settings, user_id)
    print(f"[SCHEDULER] Settings saved for user {user_id} - enabled={enabled} at {hour}:{minute:02d}")
