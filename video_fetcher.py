import os
import shutil

SAMPLE_VIDEO = os.path.join("..", "assets", "sample.mp4")


def fetch_video(output_path: str, query: str = None) -> str:
    """Fetch background video - uses local sample.mp4 for testing.
    
    Args:
        output_path: Path to save the video file
        query: Search query (unused, for compatibility)
        
    Returns:
        Path to copied video file
    """
    # Use local sample video
    sample_path = os.path.abspath(SAMPLE_VIDEO)
    if os.path.exists(sample_path):
        shutil.copy(sample_path, output_path)
        print(f"Copied sample video to {output_path}")
    else:
        raise FileNotFoundError(f"Sample video not found at {sample_path}")
    
    return output_path
