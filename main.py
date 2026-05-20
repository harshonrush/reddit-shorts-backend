import os
import sys
import tempfile
import re
import traceback
import requests
import uuid
import json
import time
import random
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
RUNPOD_URL = os.getenv("RUNPOD_URL", "https://api.runpod.ai/v2/jq2krz5bpspj1g/run")
RUNPOD_API_KEY = os.getenv("RUNPOD_API_KEY")

from script_engine import generate_script
from tts import generate_audio
from video_fetcher import fetch_video
from uploader import upload_video
from auth_routes import router as auth_router
from scheduler import update_schedule, load_settings, save_settings, daily_job
from redis_queue import video_queue, redis_conn, safe_redis_get, safe_redis_set
from rq import Retry
from db import supabase

app = FastAPI(title="Reddit Reels API")

# Videos stored in Supabase Storage (not local filesystem)

# Include auth routes
app.include_router(auth_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


class StoryboardRequest(BaseModel):
    topic: str | None = None
    script: str | None = None
    niche: str = "facts"
    language: str = "english"
    user_id: str = "default"


class SubscribeRequest(BaseModel):
    plan: str
    user_id: str = "default"


class StoryboardScene(BaseModel):
    scene_index: int
    scene_text: str
    image_prompt: str
    selected_image_url: str | None = None
    preview_images: list = []


class StoryboardResponse(BaseModel):
    script: str
    scenes: list[StoryboardScene]


class SearchPexelsRequest(BaseModel):
    query: str
    per_page: int = 5


class RegeneratePromptRequest(BaseModel):
    scene_text: str
    niche: str = "general"


class VideoJobRequest(BaseModel):
    script: str | None = None
    topic: str | None = None
    user_id: str = "default"
    niche: str = "facts"
    voice: str = "male_deep"
    video_style: str = "gameplay"
    caption_style: str = "viral"
    enable_images: bool = False
    language: str = "english"
    duration: str = "30-60"
    bg_music: str = "none"
    storyboard_scenes: list | None = None


class VideoJobResponse(BaseModel):
    job_id: str
    status: str = "queued"


class JobStatusResponse(BaseModel):
    job_id: str
    status: str  # "queued" | "processing" | "completed" | "failed"
    video_url: str | None = None
    error: str | None = None


class SeriesRequest(BaseModel):
    user_id: str
    enabled: bool = True
    niche: str = "facts"  # facts, motivation, reddit_stories, ai_stories, history
    content_mode: str = "auto"  # auto | custom
    topic: str | None = None  # user-provided topic (when content_mode=custom)
    video_style: str = "gameplay"  # gameplay, satisfying, subway, minecraft, cinematic
    voice: str = "male_deep"  # male_deep, male_calm, female_energetic, female_soft
    language: str = "english"  # english, hindi
    duration: str = "30-60"  # 15-30, 30-60, 60-90
    post_time: str = "18:30"  # HH:MM format (IST)
    frequency: str = "daily"  # daily | alternate
    enable_images: bool = False  # NEW: Enable Gemini + Pexels images
    bg_music: str = "none"


class SeriesResponse(BaseModel):
    status: str
    user_id: str
    settings: dict


class PreviewRequest(BaseModel):
    niche: str = "facts"
    topic: str | None = None
    voice: str = "male_deep"
    language: str = "english"


class PreviewResponse(BaseModel):
    script: str
    sample_captions: list
    voice_preview_url: str | None = None


def safe_filename(text):
    return re.sub(r'[^a-zA-Z0-9_-]', '_', text)[:20]


def process_video_job(
    job_id: str,
    user_id: str,
    script: str | None = None,
    topic: str | None = None,
    niche: str = "facts",
    voice: str = "male_deep",
    video_style: str = "gameplay",
    caption_style: str = "viral",
    enable_images: bool = False,
    language: str = "english",
    duration: str = "30-60",
    bg_music: str = "none",
    storyboard_scenes: list | None = None
):
    """RQ job: Process video generation via RunPod and update status."""
    try:
        # Initialize job data
        job_data = {
            "status": "processing",
            "user_id": user_id,
            "created_at": datetime.utcnow().isoformat()
        }
        if script:
            job_data["script"] = script
        if topic:
            job_data["topic"] = topic

        redis_conn.delete(job_id)
        safe_redis_set(job_id, json.dumps(job_data), ex=3600)

        # Step 1: Trigger RunPod job (async)
        print(f"[JOB {job_id}] Triggering RunPod job...")
        
        # Build standard RunPod input payload mapping all fields
        input_data = {
            "user_id": user_id,
            "niche": niche,
            "voice": voice,
            "video_style": video_style,
            "caption_style": caption_style,
            "enable_images": enable_images,
            "language": language,
            "duration": duration,
            "bg_music": bg_music
        }
        if storyboard_scenes:
            input_data["storyboard_scenes"] = storyboard_scenes
        if script:
            input_data["script"] = script
            print(f"[JOB {job_id}] Sending script to RunPod: {repr(script[:100])}...")
        if topic:
            input_data["topic"] = topic
            print(f"[JOB {job_id}] Sending topic to RunPod: {repr(topic[:100])}...")
            
        payload = {"input": input_data}
        res = requests.post(
            RUNPOD_URL,
            headers={"Authorization": f"Bearer {RUNPOD_API_KEY}"},
            json=payload,
            timeout=60
        )
        res.raise_for_status()

        result = res.json()
        print(f"[JOB {job_id}] RunPod trigger response: {result}")

        runpod_job_id = result.get("id")
        if not runpod_job_id:
            raise Exception(f"RunPod didn't return job id: {result}")

        # Step 2: Poll for completion (max 60 attempts = ~2 min)
        # Fix: RunPod status path is /status/, not /run/
        endpoint_id = RUNPOD_URL.split("/v2/")[1].replace("/run", "")
        status_url = f"https://api.runpod.ai/v2/{endpoint_id}/status/{runpod_job_id}"
        output = None

        for attempt in range(60):
            time.sleep(2)

            status_res = requests.get(
                status_url,
                headers={"Authorization": f"Bearer {RUNPOD_API_KEY}"},
                timeout=30
            )
            
            try:
                status_data = status_res.json()
            except Exception as json_err:
                print(f"[JOB {job_id}] JSON Parse Error: {json_err} | Response: {status_res.text[:200]}")
                raise Exception(f"Failed to parse RunPod response: {status_res.text[:100]}")

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
        # RunPod returns: {"output": {"video_url": "..."}}
        runpod_output = output.get("output", {})
        video_url = runpod_output.get("video_url")
        if video_url:
            # FRESH object - atomic write
            job_data = {
                "status": "completed",
                "user_id": user_id,
                "video_url": video_url,
                "completed_at": datetime.utcnow().isoformat()
            }
            if script:
                job_data["script"] = script
            if topic:
                job_data["topic"] = topic

            redis_conn.delete(job_id)
            safe_redis_set(job_id, job_data, ex=3600)
            print(f"[JOB {job_id}] Video ready: {video_url}")

            # Auto-publish manual compile to connected platforms in parallel
            try:
                from uploader import trigger_auto_publish
                post_title = topic or niche or "AI Shorts"
                trigger_auto_publish(video_url=video_url, title=post_title, user_id=user_id)
            except Exception as publish_err:
                print(f"[JOB {job_id}] Warning: Auto-publish trigger failed: {publish_err}")
        else:
            raise Exception("No video_url in RunPod output")

    except Exception as e:
        print(f"[JOB {job_id}] Error: {e}")
        # FRESH object on error - atomic write
        job_data = {
            "status": "failed",
            "user_id": user_id,
            "error": str(e)[:200],
            "failed_at": datetime.utcnow().isoformat()
        }
        if script:
            job_data["script"] = script
        if topic:
            job_data["topic"] = topic

        redis_conn.delete(job_id)
        safe_redis_set(job_id, job_data, ex=3600)


@app.post("/generate-script", response_model=ScriptResponse)
async def generate_script_endpoint(request: ScriptRequest):
    """Step 1: Generate script from idea (cheap, fast, Railway handles)."""
    try:
        # Generate script using Gemini
        script = generate_script(request.idea)

        # Store script in Redis for 24h
        script_id = f"script:{uuid.uuid4().hex[:12]}"
        safe_redis_set(script_id, script, ex=86400)

        print(f"[SCRIPT] Generated script: {repr(script[:100])}...", file=sys.stderr)
        return ScriptResponse(script=script, script_id=script_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/generate-storyboard", response_model=StoryboardResponse)
async def generate_storyboard_endpoint(request: StoryboardRequest):
    """Generate script (if empty), segment it, generate image prompts, and fetch Pexels image preview URLs."""
    try:
        # Check SaaS credit balances
        from credits_engine import get_user_credits
        user_credits = get_user_credits(request.user_id)
        if user_credits.get("credits_remaining", 0) <= 0:
            raise HTTPException(
                status_code=403,
                detail="Zero credits remaining. Please upgrade your subscription tier to create drafts."
            )

        from config import LANGUAGE_PROMPTS
        from image_generator import generate_image_prompts
        from pexels_integration import search_images

        # 1. Resolve/generate script
        script = request.script
        if not script:
            topic = request.topic or "success mindset"
            lang_prompt = LANGUAGE_PROMPTS.get(request.language, LANGUAGE_PROMPTS["english"])
            full_topic = f"{topic}. {lang_prompt}."
            script = generate_script(full_topic)

        print(f"[STORYBOARD] Generated script: {repr(script[:100])}...", file=sys.stderr)

        # 2. Generate scene-specific image prompts
        scene_prompts = generate_image_prompts(script, niche=request.niche)
        print(f"[STORYBOARD] Generated {len(scene_prompts)} scene prompts", file=sys.stderr)

        # 3. Fetch preview images for each scene
        scenes = []
        for idx, scene in enumerate(scene_prompts, 1):
            prompt_text = scene.get("image_prompt", "")
            
            # Fetch up to 4 preview images from Pexels
            pexels_results = search_images(prompt_text, per_page=4)
            if not pexels_results:
                # Fallback to first few words or niche
                fallback = " ".join(prompt_text.split()[:3]) if prompt_text else request.niche
                print(f"[STORYBOARD] Scene {idx} empty results, trying fallback: '{fallback}'", file=sys.stderr)
                pexels_results = search_images(fallback, per_page=4)

            preview_images = []
            for img in pexels_results:
                preview_images.append({
                    "url": img["url"],
                    "photographer": img["photographer"],
                    "photographer_url": img.get("photographer_url", "")
                })

            selected_url = preview_images[0]["url"] if preview_images else ""

            scenes.append({
                "scene_index": idx,
                "scene_text": scene.get("scene_text", ""),
                "image_prompt": prompt_text,
                "selected_image_url": selected_url,
                "preview_images": preview_images
            })

        return StoryboardResponse(script=script, scenes=scenes)
    except Exception as e:
        print(f"[STORYBOARD ERROR] {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/search-pexels")
async def search_pexels_endpoint(request: SearchPexelsRequest):
    """Exposes real-time Pexels image searches for interactive scene image swaps."""
    try:
        from pexels_integration import search_images
        results = search_images(request.query, per_page=request.per_page)
        return {
            "images": [
                {
                    "url": img["url"],
                    "photographer": img["photographer"],
                    "photographer_url": img.get("photographer_url", "")
                } for img in results
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/regenerate-scene-prompt")
async def regenerate_scene_prompt_endpoint(request: RegeneratePromptRequest):
    """Re-generate scene image prompt using Gemini and query fresh Pexels previews."""
    try:
        import google.generativeai as genai
        from pexels_integration import search_images
        
        model_prompt = genai.GenerativeModel("gemini-2.5-flash")
        system_prompt = f"""You are an expert at creating detailed, cinematic image prompts for short-form videos.
        
Given a scene from a {request.niche} video, generate a vivid image prompt that:
1. Is highly visual and cinematic
2. Works well for AI image generation
3. Captures the mood and emotion of the scene
4. Suggests specific visual style (cinematic, dramatic, etc.)
5. Is concise (under 100 words)

Format your response as just the image prompt, no other text."""
        
        response = model_prompt.generate_content(
            f"{system_prompt}\n\nScene: {request.scene_text}",
            generation_config=genai.types.GenerationConfig(
                temperature=0.85,
                max_output_tokens=150
            )
        )
        prompt_text = response.text.strip()
        print(f"[REGEN PROMPT] Brand new prompt generated: '{prompt_text}'", file=sys.stderr)

        pexels_results = search_images(prompt_text, per_page=4)
        if not pexels_results:
            fallback = " ".join(prompt_text.split()[:3])
            pexels_results = search_images(fallback, per_page=4)

        preview_images = [
            {
                "url": img["url"],
                "photographer": img["photographer"],
                "photographer_url": img.get("photographer_url", "")
            } for img in pexels_results
        ]

        return {
            "image_prompt": prompt_text,
            "preview_images": preview_images,
            "selected_image_url": preview_images[0]["url"] if preview_images else ""
        }
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

    # SaaS credit deduction
    from credits_engine import deduct_user_credits
    if not deduct_user_credits(request.user_id, amount=1):
        raise HTTPException(
            status_code=403,
            detail="Insufficient credits. Please upgrade your subscription tier to render videos."
        )

    if not request.script and not request.topic:
        raise HTTPException(status_code=400, detail="Must provide either 'script' or 'topic'")

    try:
        # Create truly unique job ID (no colons for URL safety)
        timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
        job_id = f"job_{timestamp}_{uuid.uuid4().hex[:8]}"

        # Store job status (atomic: delete first, then set)
        job_data = {
            "status": "queued",
            "user_id": request.user_id,
            "created_at": datetime.utcnow().isoformat()
        }
        if request.script:
            job_data["script"] = request.script
        if request.topic:
            job_data["topic"] = request.topic
            
        redis_conn.delete(job_id)
        safe_redis_set(job_id, job_data, ex=3600)

        # Enqueue job to RQ
        video_queue.enqueue(
            process_video_job,
            job_id=job_id,
            user_id=request.user_id,
            script=request.script,
            topic=request.topic,
            niche=request.niche,
            voice=request.voice,
            video_style=request.video_style,
            caption_style=request.caption_style,
            enable_images=request.enable_images,
            language=request.language,
            duration=request.duration,
            bg_music=request.bg_music,
            storyboard_scenes=request.storyboard_scenes,
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
        print(f"[DEBUG RAW REDIS] {repr(raw)}")
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
            description=request.description,
            user_id="default"  # Assuming manual upload uses default for now, or update UploadRequest to take user_id
        )
        return {"status": "uploaded", "youtube_id": res["id"], "url": f"https://youtube.com/watch?v={res['id']}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/upload-latest")
async def upload_latest(user_id: str = "default"):
    """DEPRECATED: Videos now stored in Supabase. Use video_url from job status."""
    raise HTTPException(status_code=400, detail="Use /job-status/{job_id} to get video_url")


# Startup logic handled via lifespan if needed in future


@app.get("/health")
async def health_check():
    """Health check with Redis and Supabase connectivity."""
    health = {"status": "healthy", "components": {}}

    # Check Redis
    try:
        redis_conn.ping()
        queue_len = video_queue.count
        health["components"]["redis"] = {"status": "up", "queue_depth": queue_len}
    except Exception as e:
        health["status"] = "degraded"
        health["components"]["redis"] = {"status": "down", "error": str(e)[:100]}

    # Check Supabase
    try:
        supabase.table("users_settings").select("user_id").limit(1).execute()
        health["components"]["supabase"] = {"status": "up"}
    except Exception as e:
        health["status"] = "degraded"
        health["components"]["supabase"] = {"status": "down", "error": str(e)[:100]}

    return health


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


# ==================== NEW: Improved YouTube Automation Flow ====================

@app.post("/series", response_model=SeriesResponse)
async def create_series(request: SeriesRequest):
    """Create or update a video series with full configuration."""
    try:
        # Parse post_time (HH:MM) to hour and minute
        try:
            hour, minute = map(int, request.post_time.split(":"))
        except:
            hour, minute = 18, 30
        
        # Build full settings
        settings = {
            "user_id": request.user_id,
            "enabled": request.enabled,
            "hour": hour,
            "minute": minute,
            "niche": request.niche,
            "content_mode": request.content_mode,
            "topic": request.topic if request.content_mode == "custom" else None,
            "video_style": request.video_style,
            "voice": request.voice,
            "language": request.language,
            "duration": request.duration,
            "frequency": request.frequency,
            "enable_images": request.enable_images,
            "bg_music": request.bg_music,
            "is_posting": False,
            "yt_connected": True  # Assume connected when creating series
        }
        
        # Save to database
        from scheduler import save_settings
        save_settings(request.user_id, settings)
        
        return SeriesResponse(
            status="created",
            user_id=request.user_id,
            settings=settings
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/series/{user_id}")
async def get_series(user_id: str):
    """Get series settings for a user."""
    from scheduler import load_settings
    settings = load_settings(user_id)
    return {"user_id": user_id, "settings": settings}


@app.post("/preview", response_model=PreviewResponse)
async def generate_preview(request: PreviewRequest):
    """Generate preview: script sample and captions."""
    try:
        # Generate sample script
        from script_engine import generate_script
        from scheduler import NICHE_TOPICS, LANGUAGE_PROMPTS
        
        # Get topic
        if request.topic:
            topic = request.topic
        elif request.niche in NICHE_TOPICS:
            topic = random.choice(NICHE_TOPICS[request.niche])
        else:
            topic = "interesting story"
        
        # Add language instruction
        lang_prompt = LANGUAGE_PROMPTS.get(request.language, LANGUAGE_PROMPTS["english"])
        full_topic = f"{topic}. {lang_prompt}. Make it engaging for YouTube Shorts."
        
        script = generate_script(full_topic)
        
        # Generate sample captions (first 3 lines)
        words = script.split()[:20]  # First ~20 words
        sample_captions = [
            {"text": " ".join(words[:7]), "start": 0, "end": 3},
            {"text": " ".join(words[7:14]), "start": 3, "end": 6},
            {"text": " ".join(words[14:20]), "start": 6, "end": 9}
        ]
        
        return PreviewResponse(
            script=script,
            sample_captions=sample_captions,
            voice_preview_url=None  # Could generate actual TTS preview here
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
    
    # Create lock key for this manual trigger
    from datetime import date
    lock_key = f"lock:{user_id}:{date.today().isoformat()}:manual"
    
    # Enqueue to Redis worker with lock_key
    video_queue.enqueue(
        daily_job,
        user_id,
        token_data,
        lock_key,  # Pass for cleanup
        retry=Retry(max=3, interval=[10, 30, 60]),
        job_timeout=600
    )
    
    return {"status": "triggered", "user_id": user_id, "lock_key": lock_key}


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
        
        # 🔥 ATOMIC REDIS LOCK: NX=True ensures only one process gets the lock
        lock_key = f"lock:{user_id}:{today}"
        
        # Try to acquire lock atomically (only if NOT exists) with 15 min TTL backup
        lock_acquired = redis_conn.set(lock_key, "1", nx=True, ex=900)
        if not lock_acquired:
            print(f"[CRON SKIP] {user_id} Redis lock already exists (atomic NX failed)")
            continue
        
        print(f"[CRON LOCK] Redis lock acquired: {lock_key} (TTL 15min)")
        
        # 🚨 EXTRA SAFETY: Verify our lock is still active (is_posting should be True)
        fresh_check = supabase.table("users_settings").select("is_posting").eq("user_id", user_id).execute()
        if fresh_check.data:
            check = fresh_check.data[0]
            # If is_posting is not True, another process modified it (race condition)
            if not check.get("is_posting"):
                print(f"[CRON SKIP] {user_id} lock lost (race condition)")
                redis_conn.delete(lock_key)  # Release our Redis lock
                continue
        
        # Enqueue to Redis worker with retries (pass pre-fetched token AND lock_key)
        try:
            job = video_queue.enqueue(
                daily_job,
                user_id,
                token_data,
                lock_key,  # Pass lock key for cleanup in finally
                retry=Retry(max=3, interval=[10, 30, 60]),
                job_timeout=600
            )
            print(f"[CRON ENQUEUED] Job ID: {job.id} for user {user_id}")
            triggered.append(user_id)
        except Exception as e:
            print(f"[CRON ERROR] Failed to enqueue job for {user_id}: {e}")
            import traceback
            traceback.print_exc()
            # Release locks since job failed to enqueue
            redis_conn.delete(lock_key)
            supabase.table("users_settings").update({"is_posting": False}).eq("user_id", user_id).execute()
    
    return {"status": "checked", "triggered": triggered, "time": now.isoformat()}


# ==================== NEW: Monetization & Billing Endpoints ====================

@app.get("/billing/credits")
async def get_credits(user_id: str = "default"):
    """Get the current credit balance and tier for a user."""
    from credits_engine import get_user_credits
    try:
        balance_info = get_user_credits(user_id)
        return balance_info
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/billing/subscribe")
async def subscribe_plan(request: SubscribeRequest):
    """Simulates a checkout and subscribes user to a specific tier."""
    from credits_engine import TIER_CREDITS, get_user_credits
    from redis_queue import redis_conn
    from db import supabase
    import json
    
    plan = request.plan.lower()
    
    if plan not in TIER_CREDITS:
        raise HTTPException(status_code=400, detail=f"Invalid plan. Must be one of: {list(TIER_CREDITS.keys())}")
        
    try:
        balance_info = get_user_credits(request.user_id)
        balance_info["credits_remaining"] = TIER_CREDITS[plan]
        balance_info["tier"] = plan
        
        # Save to Supabase
        try:
            supabase.table("user_credits").upsert(balance_info).execute()
        except Exception as e:
            import sys
            print(f"[BILLING ERROR] Supabase update failed: {e}", file=sys.stderr)
            
        # Save to Redis
        redis_key = f"credits:{request.user_id}"
        redis_conn.set(redis_key, json.dumps(balance_info), ex=604800)
        
        return {"status": "success", "message": f"Successfully subscribed to {plan} tier", "credits": balance_info}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)