import runpod
import sys
import tempfile
import os
import base64

from script_engine import generate_script
from tts import generate_audio
from video_fetcher import fetch_video
from subtitle import get_word_timestamps  # Deepgram transcription only
from viral_captions import generate_animated_captions  # FFmpeg viral captions


def handler(job):
    """Generate video on RunPod GPU - Railway handles upload."""
    try:
        print("[RUNPOD] Job received", file=sys.stderr)

        # Use provided script directly, or generate from topic if not provided
        script = job["input"].get("script")
        if not script:
            topic = job["input"].get("topic", "success mindset")
            script = generate_script(topic)
            print(f"[RUNPOD] Generated script from topic: {topic}", file=sys.stderr)
        else:
            print(f"[RUNPOD] Using provided script: {script[:50]}...", file=sys.stderr)

        # 3. Temp files (secure)
        audio_path = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False).name
        video_path = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False).name
        output_path = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False).name

        # 4. Pipeline
        generate_audio(script, audio_path)
        fetch_video(video_path)
        
        # 5. Get word timestamps from Deepgram
        words = get_word_timestamps(audio_path)
        print(f"[RUNPOD] Got {len(words)} words for captions", file=sys.stderr)
        
        # 6. Generate viral captions with FFmpeg (big text + zoom effects)
        generate_animated_captions(video_path, audio_path, words, output_path)

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
