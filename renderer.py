import subprocess
import shutil
import os

# Detect OS and use appropriate temp path
IS_WINDOWS = os.name == 'nt'
TEMP_DIR = "C:/temp" if IS_WINDOWS else "/tmp"

def render_video(audio, video, subtitles, output, max_duration=60):
    """Render video with optimized settings for Railway deployment."""
    
    os.makedirs(TEMP_DIR, exist_ok=True)

    # Copy subtitles to safe temp location (Railway/Linux compatible)
    safe_sub = os.path.join(TEMP_DIR, "sub.ass")
    shutil.copy(subtitles, safe_sub)
    
    # Escape colon for FFmpeg filter (Windows only needs this)
    if IS_WINDOWS:
        safe_sub_escaped = safe_sub.replace(":", "\\:")
    else:
        safe_sub_escaped = safe_sub

    # Optimized video filter: lower resolution, reduced quality
    vf = f"scale=720:1280,ass='{safe_sub_escaped}'"

    cmd = [
        "ffmpeg",
        "-y",
        "-stream_loop", "-1",
        "-i", video,
        "-i", audio,

        # Map video from background, audio from TTS
        "-map", "0:v:0",
        "-map", "1:a:0",
        
        # Video: lower quality for faster encoding + less RAM
        "-c:v", "libx264",
        "-preset", "veryfast",  # Fast encoding
        "-crf", "28",           # Lower quality = smaller file, less RAM
        
        # Audio: reduced bitrate
        "-c:a", "aac",
        "-b:a", "128k",
        
        # Subtitles and duration
        "-vf", vf,
        "-t", str(max_duration),
        "-shortest",

        output
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True)
        print(f"✅ Rendered: {output}")
        return output
    except subprocess.CalledProcessError as e:
        print("❌ FFMPEG FAILED:", e)
        print("STDERR:", e.stderr.decode() if e.stderr else "N/A")
        return None