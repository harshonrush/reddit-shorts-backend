"""Auto-posting scheduler for daily video generation and upload."""
import random
import os
import logging
import time
import requests
from datetime import datetime

# RunPod Serverless Configuration
RUNPOD_URL = os.getenv("RUNPOD_URL", "https://api.runpod.ai/v2/jq2krz5bpspj1g/run")
RUNPOD_API_KEY = os.getenv("RUNPOD_API_KEY")

def trigger_render(topic: str, user_id: str, token_data: dict, settings: dict = None) -> dict:
    """Trigger video rendering on RunPod serverless GPU with full settings."""
    if not RUNPOD_API_KEY:
        print(f"[RUNPOD] ERROR: No API key configured")
        return {"status": "error", "message": "Missing RUNPOD_API_KEY"}

    try:
        # Build input with all settings
        input_data = {
            "topic": topic,
            "user_id": user_id,
            "token_data": token_data,  # Pass user token for upload
        }
        
        # Add optional settings if provided
        if settings:
            input_data["voice"] = settings.get("voice", "male_deep")
            input_data["language"] = settings.get("language", "english")
            input_data["video_style"] = settings.get("video_style", "gameplay")
            input_data["duration"] = settings.get("duration", "30-60")
        
        print(f"[RUNPOD] Triggering render for user {user_id}, topic: {topic}, voice: {input_data.get('voice')}")
        res = requests.post(
            RUNPOD_URL,
            headers={
                "Authorization": f"Bearer {RUNPOD_API_KEY}",
                "Content-Type": "application/json"
            },
            json={"input": input_data},
            timeout=60  # Increased for cold start
        )
        result = res.json()
        print(f"[RUNPOD] Response: {result}")
        return result
    except Exception as e:
        print(f"[RUNPOD] ERROR: {e}")
        return {"status": "error", "message": str(e)}


def poll_runpod_status(job_id: str, user_id: str, max_wait: int = 600) -> dict:
    """Poll RunPod job status until COMPLETED or timeout."""
    # Extract endpoint ID from RUNPOD_URL
    # URL format: https://api.runpod.ai/v2/ENDPOINT_ID/run
    endpoint_id = RUNPOD_URL.split("/v2/")[1].replace("/run", "")
    status_url = f"https://api.runpod.ai/v2/{endpoint_id}/status/{job_id}"

    print(f"[RUNPOD] Polling status for job {job_id}...")
    start_time = time.time()

    while time.time() - start_time < max_wait:
        try:
            res = requests.get(
                status_url,
                headers={"Authorization": f"Bearer {RUNPOD_API_KEY}"},
                timeout=10
            )
            status_data = res.json()
            status = status_data.get("status")
            print(f"[RUNPOD] Job {job_id} status: {status}")

            if status == "COMPLETED":
                output = status_data.get("output", {})
                # RunPod returns: {"output": {"video_url": "..."}}
                runpod_data = output.get("output", {})
                video_url = runpod_data.get("video_url")
                if video_url:
                    print(f"[RUNPOD] Video ready at {video_url}")
                    return {"success": True, "video_url": video_url}
                else:
                    error_msg = output.get("message", "Unknown error")
                    print(f"[RUNPOD] Job {job_id} failed: {error_msg}")
                    return {"success": False, "error": error_msg}

            elif status in ["FAILED", "CANCELLED", "TIMED_OUT"]:
                print(f"[RUNPOD] Job {job_id} {status}")
                return {"success": False, "error": f"Job {status}"}

            # Still running - wait 10 seconds before next poll
            time.sleep(10)

        except Exception as e:
            print(f"[RUNPOD] Polling error: {e}")
            time.sleep(10)

    # Timeout reached
    print(f"[RUNPOD] Timeout waiting for job {job_id}")
    return {"success": False, "error": "Polling timeout"}

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Niche-based topic mapping (expanded)
NICHE_TOPICS = {
    "facts": ["amazing facts", "did you know", "mind blowing facts", "science facts", "history facts"],
    "motivation": ["discipline", "morning routine", "success mindset", "never give up", "transformation"],
    "reddit_stories": ["creepy encounter", "strange neighbor", "mystery solved", "unexpected twist", "life changing moment"],
    "ai_stories": ["futuristic story", "AI takeover", "robot romance", "virtual reality", "digital consciousness"],
    "history": ["ancient mysteries", "war stories", "forgotten history", "historical figures", "empire rise and fall"],
    "heartbreak": ["heartbreak", "breakup recovery", "moving on", "lost love", "emotional healing"],
    "business": ["startup struggle", "entrepreneur journey", "side hustle success", "business betrayal", "rags to riches"],
    "fitness": ["gym discipline", "weight loss journey", "fitness transformation", "mental strength", "health wake-up call"],
    "stories": ["creepy encounter", "strange neighbor", "mystery solved", "unexpected twist", "life changing moment"]
}

# Voice mapping (user-friendly names → ElevenLabs IDs)
VOICE_MAP = {
    "male_deep": "pNInz6obpgDQGcFmaJgB",      # Adam
    "male_calm": "IKne3meq5aSn9XLyUdCD",      # Antoni
    "female_energetic": "EXAVITQu4vr4xnSDxMaL",  # Bella
    "female_soft": "MF3mGyEYCl7XYWbV9V6O"       # Elli
}

# Language prompts for script generation
LANGUAGE_PROMPTS = {
    "english": "Generate in English",
    "hindi": "Generate in Hindi language using Devanagari script",
    "hinglish": "Generate in Hinglish (Hindi written in English/Roman script)"
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

    # CREATE ROW IF NOT EXISTS - with new fields
    default_data = {
        "user_id": user_id,
        "enabled": False,
        "hour": 18,
        "minute": 0,
        "niche": "stories",
        "content_mode": "auto",  # auto | custom
        "custom_topic": None,
        "video_style": "gameplay",  # gameplay | satisfying | subway | minecraft | cinematic
        "voice": "male_deep",  # male_deep | male_calm | female_energetic | female_soft
        "language": "english",  # english | hindi | hinglish
        "duration": "30-60",  # 15-30 | 30-60 | 60-90
        "frequency": "daily",  # daily | alternate
        "last_posted_date": None,
        "is_posting": False,
        "yt_connected": False,
        "channel_id": None
    }

    supabase.table("users_settings").insert(default_data).execute()

    return default_data


def safe_update(table: str, user_id: str, updates: dict):
    """Safely update Supabase with error handling."""
    try:
        res = supabase.table(table) \
            .update(updates) \
            .eq("user_id", user_id) \
            .execute()
        print(f"[DB] Updated {table} for {user_id}: {list(updates.keys())}")
        return res
    except Exception as e:
        print(f"[DB ERROR] Failed to update {table} for {user_id}: {e}")
        raise


def save_settings(user_id: str, updates: dict):
    """Save auto-post settings for a user to Supabase."""
    try:
        # Use UPDATE instead of UPSERT for existing records
        res = supabase.table("users_settings") \
            .update(updates) \
            .eq("user_id", user_id) \
            .execute()

        if res.data:
            print(f"[DB] Updated settings for {user_id}: {list(updates.keys())}")
        else:
            print(f"[DB] WARNING: No rows updated for {user_id}")
            # Try insert as fallback
            updates["user_id"] = user_id
            res = supabase.table("users_settings").insert(updates).execute()
            print(f"[DB] Inserted new settings for {user_id}")
    except Exception as e:
        print(f"[DB] ERROR saving settings for {user_id}: {e}")
        raise


def token_exists(user_id: str) -> bool:
    """Check if user has stored YouTube token in Supabase."""
    res = supabase.table("user_tokens") \
        .select("*") \
        .eq("user_id", user_id) \
        .execute()
    return len(res.data) > 0


def daily_job(user_id: str, token_data: dict = None):
    """Orchestrate daily video generation via RunPod serverless GPU."""
    print(f"[WORKER] daily_job STARTED for user {user_id}")

    try:
        settings = load_settings(user_id)
        if not settings.get("enabled", False):
            logger.info(f"[USER:{user_id}] Auto-post disabled, skipping.")
            print(f"[WORKER] daily_job SKIPPED (disabled) for {user_id}")
            return

        # Check if token provided (cron passes it, manual/trigger may not)
        if not token_data:
            logger.warning(f"[USER:{user_id}] No token_data provided, skipping.")
            print(f"[WORKER] daily_job SKIPPED (no token) for {user_id}")
            save_settings(user_id, {"is_posting": False, "last_error": "No token provided"})
            return

        # Check frequency - skip if not daily and already posted recently
        frequency = settings.get("frequency", "daily")
        last_posted = settings.get("last_posted_date")
        if frequency == "alternate" and last_posted:
            from datetime import datetime, timedelta
            last_date = datetime.strptime(last_posted, "%Y-%m-%d")
            if (datetime.utcnow() - last_date).days < 2:
                print(f"[SCHEDULER] [USER:{user_id}] Skipping (alternate days, last posted {last_posted})")
                save_settings(user_id, {"is_posting": False})
                return
        
        # Pick topic based on content mode
        content_mode = settings.get("content_mode", "auto")
        if content_mode == "custom" and settings.get("custom_topic"):
            topic = settings.get("custom_topic")
            niche = "custom"
        else:
            # Auto mode - pick from niche
            niche = settings.get("niche", "stories")
            if niche in NICHE_TOPICS:
                topic = random.choice(NICHE_TOPICS[niche])
            else:
                topic = random.choice(TOPICS)
        
        # Get voice and language settings
        voice = settings.get("voice", "male_deep")
        language = settings.get("language", "english")
        video_style = settings.get("video_style", "gameplay")
        duration = settings.get("duration", "30-60")
        
        print(f"[SCHEDULER] [USER:{user_id}] Niche: {niche} | Topic: {topic} | Voice: {voice} | Lang: {language} | Style: {video_style}")

        # TRIGGER RUNPOD SERVERLESS GPU (with full settings)
        result = trigger_render(topic, user_id, token_data, settings)

        if result.get("id"):
            job_id = result.get("id")
            print(f"[RUNPOD] Job queued for {user_id}: {job_id}")

            # POLL until job completes (max 10 minutes)
            poll_result = poll_runpod_status(job_id, user_id, max_wait=600)

            if poll_result.get("success"):
                video_url = poll_result.get("video_url")
                print(f"[RUNPOD] Video ready at {video_url}")

                # Upload to YouTube using user's token
                from uploader import upload_video
                res = upload_video(
                    video_url=video_url,
                    title=f"{topic.title()} Story",
                    description=f"#{niche} #shorts #viral",
                    token_data=token_data
                )

                if res:
                    print(f"[UPLOAD] Video uploaded: https://youtube.com/watch?v={res['id']}")
                    save_settings(user_id, {
                        "is_posting": False,
                        "last_posted_date": datetime.utcnow().strftime("%Y-%m-%d"),
                        "last_error": None
                    })
                else:
                    print(f"[UPLOAD] Failed for {user_id}")
                    save_settings(user_id, {"is_posting": False, "last_error": "Upload failed"})
            else:
                print(f"[RUNPOD] Job failed for {user_id}: {poll_result.get('error')}")
                save_settings(user_id, {
                    "is_posting": False,
                    "last_error": f"RunPod failed: {poll_result.get('error', 'Unknown')[:100]}"
                })
        else:
            error_msg = result.get("message", "Unknown error")
            print(f"[RUNPOD] Failed to queue job for {user_id}: {error_msg}")
            save_settings(user_id, {
                "is_posting": False,
                "last_error": f"RunPod trigger failed: {error_msg[:100]}"
            })

    except Exception as e:
        logger.error(f"[USER:{user_id}] Error in daily_job: {e}")
        import traceback
        logger.error(f"[USER:{user_id}] {traceback.format_exc()}")
        save_settings(user_id, {
            "is_posting": False,
            "last_error": str(e)[:200]
        })
    finally:
        print(f"[WORKER] daily_job ENDED for {user_id}")


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
