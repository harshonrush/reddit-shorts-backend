import os
import shutil
import requests

SAMPLE_VIDEO = os.path.join("..", "assets", "sample.mp4")

# Public domain sample video URL (fallback)
SAMPLE_VIDEO_URL = "https://samplelib.com/lib/preview/mp4/sample-5s.mp4"


def fetch_video(output_path: str, query: str = None) -> str:
    """Fetch background video - uses local sample.mp4 or downloads from URL.
    
    Args:
        output_path: Path to save the video file
        query: Search query (unused, for compatibility)
        
    Returns:
        Path to video file
    """
    # Try local sample video first
    sample_path = os.path.abspath(SAMPLE_VIDEO)
    if os.path.exists(sample_path):
        shutil.copy(sample_path, output_path)
        print(f"Copied local sample video to {output_path}")
        return output_path
    
    # Download sample video from URL
    print(f"Local sample not found, downloading from URL...")
    try:
        response = requests.get(SAMPLE_VIDEO_URL, stream=True, timeout=30)
        response.raise_for_status()
        
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        print(f"Downloaded sample video to {output_path}")
        return output_path
    except Exception as e:
        print(f"Failed to download video: {e}")
        # Last resort: create a blank video with ffmpeg
        return create_blank_video(output_path)


def create_blank_video(output_path: str, duration: int = 5) -> str:
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
        subprocess.run(cmd, capture_output=True, check=True)
        print(f"Created blank video at {output_path}")
        return output_path
    except Exception as e:
        raise RuntimeError(f"Failed to create video: {e}")
