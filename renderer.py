import subprocess
import shutil
import os

def render_video(audio, video, subtitles, output, max_duration=90):

    os.makedirs("C:/temp", exist_ok=True)

    safe_sub = "C:/temp/sub.ass"
    shutil.copy(subtitles, safe_sub)

    safe_sub = safe_sub.replace(":", "\\:")

    vf = f"scale=1080:1920,ass='{safe_sub}'"

    cmd = [
        "ffmpeg",
        "-y",
        "-stream_loop", "-1",
        "-i", video,
        "-i", audio,

        # 🔥 IMPORTANT FIXES
        "-map", "0:v:0",   # take video from background
        "-map", "1:a:0",   # take audio from TTS
        "-c:v", "libx264",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",

        "-vf", vf,
        "-t", str(max_duration),

        output
    ]

    subprocess.run(cmd, check=True)