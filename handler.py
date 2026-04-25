import runpod
from script_engine import generate_story, generate_script
from tts import generate_audio
from video_fetcher import fetch_video
from subtitle_ass import generate_ass
from renderer import render_video
from uploader import upload_video

import tempfile
import os

def handler(job):
    try:
        topic = job["input"].get("topic", "success mindset")
        token_data = job["input"].get("token_data")  # User's YouTube token

        # 1. Story
        story = generate_story(topic)

        # 2. Script
        script = generate_script(story)

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

        # 6. Output
        output_path = f"/tmp/output_{topic}.mp4"
        render_video(audio_path, video_path, ass_path, output_path)

        # 7. Upload using USER'S token (uploads to their channel)
        res = upload_video(
            file_path=output_path,
            title="Crazy Story",
            description="#shorts #viral",
            token_data=token_data  # Pass user token for upload
        )

        return {
            "status": "success",
            "video_url": f"https://youtube.com/watch?v={res['id']}"
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}

# 🔥 THIS LINE IS REQUIRED
runpod.serverless.start({"handler": handler})
