import runpod
import sys
import tempfile
import os

from script_engine import generate_script
from tts import generate_audio
from video_fetcher import fetch_video
from subtitle import get_word_timestamps  # Deepgram transcription only
from viral_captions import generate_animated_captions  # FFmpeg viral captions
from storage import upload_video_bytes  # Direct upload to Supabase

# Voice mapping (user-friendly → ElevenLabs ID)
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


def handler(job):
    """Generate video on RunPod GPU - Railway handles upload."""
    try:
        print("[RUNPOD] Job received", file=sys.stderr)

        # Get settings from input
        voice = job["input"].get("voice", "male_deep")
        language = job["input"].get("language", "english")
        video_style = job["input"].get("video_style", "gameplay")
        
        # Map voice to ElevenLabs ID
        voice_id = VOICE_MAP.get(voice, VOICE_MAP["male_deep"])
        
        # Use provided script directly, or generate from topic if not provided
        script = job["input"].get("script")
        if not script:
            topic = job["input"].get("topic", "success mindset")
            # Add language instruction to topic
            lang_prompt = LANGUAGE_PROMPTS.get(language, LANGUAGE_PROMPTS["english"])
            full_topic = f"{topic}. {lang_prompt}."
            script = generate_script(full_topic)
            print(f"[RUNPOD] Generated script from topic: {topic} (lang: {language})", file=sys.stderr)
        else:
            print(f"[RUNPOD] Using provided script: {script[:50]}...", file=sys.stderr)

        # 3. Temp files (secure)
        audio_path = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False).name
        video_path = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False).name
        output_path = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False).name

        # 4. Pipeline with voice and style
        print(f"[RUNPOD] Step 1: Generating audio with voice {voice_id}...", file=sys.stderr)
        generate_audio(script, audio_path, voice_id=voice_id)
        audio_size = os.path.getsize(audio_path)
        print(f"[RUNPOD] Audio generated: {audio_size} bytes", file=sys.stderr)
        if audio_size < 1000:
            raise Exception(f"Audio file too small ({audio_size} bytes) - TTS failed")
        
        print(f"[RUNPOD] Step 2: Fetching video with style {video_style}...", file=sys.stderr)
        fetch_video(video_path, style=video_style)
        video_size = os.path.getsize(video_path)
        print(f"[RUNPOD] Video fetched: {video_size} bytes", file=sys.stderr)
        if video_size < 10000:
            raise Exception(f"Video file too small ({video_size} bytes) - fetch failed")
        
        # 5. Get word timestamps from Deepgram
        print(f"[RUNPOD] Step 3: Getting word timestamps...", file=sys.stderr)
        words = get_word_timestamps(audio_path)
        print(f"[RUNPOD] Got {len(words)} words for captions", file=sys.stderr)
        if not words:
            print(f"[RUNPOD WARNING] No words detected - captions will be empty", file=sys.stderr)
        
        # 6. Generate viral captions with FFmpeg (big text + zoom effects)
        print(f"[RUNPOD] Step 4: Generating animated captions...", file=sys.stderr)
        generate_animated_captions(video_path, audio_path, words, output_path)
        output_size = os.path.getsize(output_path)
        print(f"[RUNPOD] Output video: {output_size} bytes", file=sys.stderr)
        if output_size < 10000:
            raise Exception(f"Output video too small ({output_size} bytes) - caption generation failed")

        print("[RUNPOD] Video rendered successfully", file=sys.stderr)

        # Read video and upload directly to Supabase Storage
        with open(output_path, "rb") as f:
            video_bytes = f.read()
        
        user_id = job["input"].get("user_id", "anonymous")
        job_id = job["id"]
        video_url = upload_video_bytes(video_bytes, user_id, job_id)

        print(f"[RUNPOD] Video uploaded: {video_url}", file=sys.stderr)
        print(f"FINAL OUTPUT: {video_url}", file=sys.stderr)

        return {
            "output": {
                "video_url": video_url
            }
        }

    except Exception as e:
        print(f"[RUNPOD ERROR] {e}", file=sys.stderr)
        return {"status": "error", "message": str(e)}


runpod.serverless.start({"handler": handler})
