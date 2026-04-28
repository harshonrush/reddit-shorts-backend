import runpod
import sys
import tempfile
import os
import base64

from script_engine import generate_script
from tts import generate_audio
from video_fetcher import fetch_video
from subtitle_ass import generate_ass
from renderer import render_video


def handler(job):
    """Generate video on RunPod GPU - Railway handles upload."""
    try:
        print("[RUNPOD] Job received", file=sys.stderr)

        topic = job["input"].get("topic", "success mindset")

        # Generate script directly from topic
        script = generate_script(topic)

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

        # Read and encode video to base64
        with open(output_path, "rb") as f:
            video_bytes = f.read()
        video_base64 = base64.b64encode(video_bytes).decode("utf-8")

        print(f"[RUNPOD] Video encoded to base64 ({len(video_base64)} chars)", file=sys.stderr)

        return {
            "status": "success",
            "video": video_base64
        }

    except Exception as e:
        print(f"[RUNPOD ERROR] {e}", file=sys.stderr)
        return {"status": "error", "message": str(e)}


runpod.serverless.start({"handler": handler})
