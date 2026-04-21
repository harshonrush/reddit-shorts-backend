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

    # Ultra-low quality for Railway free tier (512MB RAM)
    vf = f"scale=480:854,ass='{safe_sub_escaped}'"

    cmd = [
        "ffmpeg",
        "-y",
        "-stream_loop", "-1",
        "-i", video,
        "-i", audio,

        # Map video from background, audio from TTS
        "-map", "0:v:0",
        "-map", "1:a:0",
        
        # Video: ULTRA low quality for 512MB RAM
        "-c:v", "libx264",
        "-preset", "ultrafast",  # Fastest encoding
        "-crf", "35",             # Very low quality = less RAM
        "-threads", "1",          # Single thread = less RAM
        "-max_muxing_queue_size", "1024",
        
        # Audio: minimal bitrate
        "-c:a", "aac",
        "-b:a", "96k",
        
        # Subtitles and duration
        "-vf", vf,
        "-t", "30",               # Shorter duration
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