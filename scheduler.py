"""Auto-posting scheduler for daily video generation and upload."""
import random
import os
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


from db import supabase

def load_settings(user_id: str):
    """Load auto-post settings for a user from Supabase."""
    res = supabase.table("users_settings") \
        .select("*") \
        .eq("user_id", user_id) \
        .execute()

    if res.data:
        return res.data[0]

    # CREATE ROW IF NOT EXISTS
    default_data = {
        "user_id": user_id,
        "enabled": False,
        "hour": 18,
        "minute": 0,
        "niche": "stories",
        "last_posted_date": None,
        "is_posting": False
    }

    supabase.table("users_settings").insert(default_data).execute()

    return default_data


def save_settings(user_id: str, updates: dict):
    """Save auto-post settings for a user to Supabase."""
    updates["user_id"] = user_id

    res = supabase.table("users_settings") \
        .upsert(updates, on_conflict="user_id") \
        .execute()

    print("UPSERT RESULT:", res.data)


def token_exists(user_id: str) -> bool:
    """Check if user has stored YouTube token in Supabase."""
    res = supabase.table("user_tokens") \
        .select("*") \
        .eq("user_id", user_id) \
        .execute()
    return len(res.data) > 0


def daily_job(user_id: str, token_data: dict = None):
    """Generate and upload video daily."""
    settings = load_settings(user_id)
    if not settings.get("enabled", False):
        logger.info(f"[USER:{user_id}] Auto-post disabled, skipping.")
        return
    
    # Check if token provided (cron passes it, manual/trigger may not)
    if not token_data:
        logger.warning(f"[USER:{user_id}] No token_data provided, skipping.")
        return
    
    # Pick topic based on user's niche
    niche = settings.get("niche", "stories")
    if niche in NICHE_TOPICS:
        topic = random.choice(NICHE_TOPICS[niche])
    else:
        topic = random.choice(TOPICS)
    print(f"[SCHEDULER] [USER:{user_id}] Niche: {niche} | Topic: {topic}")
    
    start_time = time.time()
    def check_timeout():
        if time.time() - start_time > 300:
            raise Exception("Job timeout")
    
    audio_path = video_path = ass_path = None
    try:
        # Import here to avoid circular imports
        from tts import generate_audio
        from video_fetcher import fetch_video
        from subtitle_ass import generate_ass
        from renderer import render_video
        from uploader import upload_video
        import tempfile
        
        OUTPUT_DIR = os.path.abspath(os.path.join("..", "assets", "output"))
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        
        # 1. Generate script directly from topic (single API call)
        from script_engine import generate_script
        script = generate_script(topic)

        check_timeout()

        # 2. Audio
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            audio_path = f.name
        generate_audio(script, audio_path)
        
        check_timeout()

        # 3. Video
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            video_path = f.name
            
        try:
            fetch_video(video_path)
        except Exception as e:
            logger.error(f"[USER:{user_id}] Video fetch failed: {e}. Using light video fallback.")
            try:
                from video_fetcher import create_blank_video
                create_blank_video(video_path)
            except Exception as inner_e:
                logger.error(f"[USER:{user_id}] Fallback video creation failed: {inner_e}")
                raise
        
        check_timeout()
        
        # 4. Subtitles
        with tempfile.NamedTemporaryFile(suffix=".ass", delete=False) as f:
            ass_path = f.name
        generate_ass(script, audio_path, ass_path)
        
        # 5. Render (per-user folder)
        user_output_dir = os.path.join(OUTPUT_DIR, user_id)
        os.makedirs(user_output_dir, exist_ok=True)
        filename = f"auto_reel_{topic.replace(' ', '_')}.mp4"
        output_path = os.path.join(user_output_dir, filename)
        result = render_video(audio_path, video_path, ass_path, output_path, max_duration=60)
        
        if not result:
            print(f"[SCHEDULER] ❌ Render failed for user {user_id}")
            return
            
        check_timeout()
        

        # 6. Upload to YouTube (with retry)
        logger.info(f"[USER:{user_id}] Uploading to YouTube...")
        res = None
        for attempt in range(3):
            try:
                res = upload_video(
                    file_path=output_path,
                    title=f"Crazy {topic.title()} Story",
                    description=f"#{topic.replace(' ', '')} #shorts #reddit #storytime",
                    tags=["reddit", "story", "shorts", topic],
                    user_id=user_id,
                    token_data=token_data
                )
                print(f"[USER:{user_id}] UPLOAD SUCCESS: {res}")
                break
            except Exception as e:
                logger.error(f"[USER:{user_id}] Upload attempt {attempt + 1} failed: {e}")
                print(f"[USER:{user_id}] UPLOAD FAILED: {str(e)}")
                if attempt == 2:  # Last attempt
                    logger.error(f"[USER:{user_id}] All upload attempts failed")
                    
                    # 🔥 IMPORTANT: UNLOCK USER (prevent stuck state)
                    save_settings(user_id, {"is_posting": False, "last_error": "Upload failed after 3 attempts"})
                    
                    return
                time.sleep(5)  # Wait 5s before retry

        if res:
            logger.info(f"[USER:{user_id}] Posted: https://youtube.com/watch?v={res['id']}")
            # Mark complete: unlock, set last_posted_date, clear error
            from datetime import datetime
            save_settings(user_id, {
                "is_posting": False,
                "last_posted_date": datetime.utcnow().strftime("%Y-%m-%d"),
                "last_error": None
            })
        else:
            logger.error(f"[USER:{user_id}] Upload returned no response")
            # Unlock only (no last_posted_date, allows retry on next cron tick)
            save_settings(user_id, {"is_posting": False})
        
    except Exception as e:
        logger.error(f"[USER:{user_id}] Error in daily_job: {e}")
        import traceback
        logger.error(f"[USER:{user_id}] {traceback.format_exc()}")
        
        # Unlock and record error (no last_posted_date, allows retry)
        save_settings(user_id, {
            "is_posting": False,
            "last_error": str(e)[:200]
        })
    finally:
        try:
            # 🔥 FAIL-SAFE: Ensure user is never stuck in is_posting=True state
            save_settings(user_id, {"is_posting": False})
        except:
            pass

        for f in [audio_path, video_path, ass_path]:
            try:
                if f and os.path.exists(f):
                    os.remove(f)
            except:
                pass


def update_schedule(enabled: bool, hour: int, minute: int, user_id: str, niche: str):
    updates = {
        "user_id": user_id,
        "enabled": enabled,
        "hour": hour,
        "minute": minute,
        "niche": niche
    }

    res = supabase.table("users_settings") \
        .upsert(updates, on_conflict="user_id") \
        .execute()

    print("UPSERT RESULT:", res.data)
    logger.info(f"[USER:{user_id}] Settings saved - enabled={enabled} at {hour}:{minute:02d}")
