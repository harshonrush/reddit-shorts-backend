import os
import shutil
import requests

SAMPLE_VIDEO = os.path.join("..", "assets", "sample.mp4")

# Video style URLs (stored in Supabase Storage)
VIDEO_STYLES = {
    "gameplay": "https://jcsczgrtoocugekkvkbs.supabase.co/storage/v1/object/public/videos/default/6150661-uhd_2160_4096_25fps.mp4",
    "satisfying": "https://jcsczgrtoocugekkvkbs.supabase.co/storage/v1/object/public/videos/default/6150661-uhd_2160_4096_25fps.mp4",
    "subway": "https://jcsczgrtoocugekkvkbs.supabase.co/storage/v1/object/public/videos/default/6150661-uhd_2160_4096_25fps.mp4",
    "minecraft": "https://jcsczgrtoocugekkvkbs.supabase.co/storage/v1/object/public/videos/default/6150661-uhd_2160_4096_25fps.mp4",
    "cinematic": "https://jcsczgrtoocugekkvkbs.supabase.co/storage/v1/object/public/videos/default/6150661-uhd_2160_4096_25fps.mp4"
}

# Default fallback
DEFAULT_STYLE = "gameplay"


def fetch_video(output_path: str, style: str = None, query: str = None) -> str:
    """Fetch background video - uses style-specific URL or local sample.
    
    Args:
        output_path: Path to save the video file
        style: Video style (gameplay, satisfying, subway, minecraft, cinematic)
        query: Search query (unused, for compatibility)
        
    Returns:
        Path to video file
    """
    # Get style-specific URL
    video_url = VIDEO_STYLES.get(style, VIDEO_STYLES[DEFAULT_STYLE])
    print(f"[VIDEO] Using style: {style or DEFAULT_STYLE} -> {video_url}")
    
    # Try local sample video first (if exists)
    sample_path = os.path.abspath(SAMPLE_VIDEO)
    if os.path.exists(sample_path):
        shutil.copy(sample_path, output_path)
        print(f"Copied local sample video to {output_path}")
        return output_path
    
    # Download style-specific video from URL
    print(f"[VIDEO] Downloading from URL...")
    try:
        response = requests.get(video_url, stream=True, timeout=30)
        response.raise_for_status()
        
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        print(f"[VIDEO] Downloaded to {output_path}")
        return output_path
    except Exception as e:
        print(f"[VIDEO] Failed to download: {e}")
        import traceback
        traceback.print_exc()
        # Last resort: create a blank video with ffmpeg
        print(f"[VIDEO] Falling back to blank video creation...")
        return create_blank_video(output_path)


def create_blank_video(output_path: str, duration: int = 60) -> str:
    """Create a blank colored video using ffmpeg as last resort."""
    import subprocess
    
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"color=c=black:s=360x640:d={duration}",
        "-f", "lavfi",
        "-i", "anullsrc=r=22050:cl=mono",
        "-shortest",
        "-pix_fmt", "yuv420p",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        output_path
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, check=True)
        print(f"[VIDEO] Created blank video at {output_path}")
        return output_path
    except subprocess.CalledProcessError as e:
        print(f"[VIDEO ERROR] FFmpeg failed: {e}")
        print(f"[VIDEO ERROR] stderr: {e.stderr.decode() if e.stderr else 'None'}")
        print(f"[VIDEO ERROR] stdout: {e.stdout.decode() if e.stdout else 'None'}")
        raise RuntimeError(f"Failed to create video: {e}")
    except Exception as e:
        print(f"[VIDEO ERROR] Unexpected error creating video: {e}")
        import traceback
        traceback.print_exc()
        raise RuntimeError(f"Failed to create video: {e}")
