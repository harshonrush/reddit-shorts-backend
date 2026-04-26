import runpod
import sys
import tempfile
import os

from script_engine import generate_story, generate_script
from tts import generate_audio
from video_fetcher import fetch_video
from subtitle_ass import generate_ass
from renderer import render_video


def handler(job):
    """Generate video on RunPod GPU - Railway handles upload."""
    try:
        print("[RUNPOD] Job received", file=sys.stderr)

        topic = job["input"].get("topic", "success mindset")

        # 1. Story
        story = generate_story(topic)

        # 2. Script
        script = generate_script(story)

        # 3. Temp files
        audio_path = tempfile.mktemp(suffix=".mp3")
        video_path = tempfile.mktemp(suffix=".mp4")
        ass_path = tempfile.mktemp(suffix=".ass")
        output_path = tempfile.mktemp(suffix=".mp4")

        # 4. Pipeline
        generate_audio(script, audio_path)
        fetch_video(video_path)
        generate_ass(script, audio_path, ass_path)
        render_video(audio_path, video_path, ass_path, output_path)

        print("[RUNPOD] Video rendered successfully", file=sys.stderr)

        # Return video path - Railway will download and upload
        return {
            "status": "success",
            "video_path": output_path
        }

    except Exception as e:
        print(f"[RUNPOD ERROR] {e}", file=sys.stderr)
        return {"status": "error", "message": str(e)}


runpod.serverless.start({"handler": handler})
