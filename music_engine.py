import os
import sys
import requests
from config import MUSIC_MAP

# Cache directory: backend/assets/music/
MUSIC_DIR = os.path.join(os.path.dirname(__file__), "assets", "music")

def fetch_background_music(style: str) -> str | None:
    """Fetch background music track - checks local cache, downloads if missing.
    
    Args:
        style: Name of the music style (lofi, dark_ambient, upbeat, cinematic)
        
    Returns:
        Absolute path to the downloaded/cached audio file, or None if disabled/failed
    """
    if not style or style.lower() == "none":
        print(f"[MUSIC ENGINE] Background music is disabled.")
        return None
        
    style_key = style.lower().strip()
    if style_key not in MUSIC_MAP:
        print(f"[MUSIC ENGINE] Warning: Unknown music style '{style}'. Disabling music.")
        return None
        
    url = MUSIC_MAP[style_key]
    
    # Create cache directory if it doesn't exist
    os.makedirs(MUSIC_DIR, exist_ok=True)
    
    # File name is style name + extension
    filename = f"{style_key}.mp3"
    local_path = os.path.abspath(os.path.join(MUSIC_DIR, filename))
    
    # Return immediately if file is cached
    if os.path.exists(local_path):
        print(f"[MUSIC ENGINE] Using cached music file: {local_path} ({os.path.getsize(local_path)} bytes)")
        return local_path
        
    # Download file dynamically
    print(f"[MUSIC ENGINE] Fetching '{style_key}' music track from {url}...")
    try:
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()
        
        with open(local_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                
        file_size = os.path.getsize(local_path)
        print(f"[MUSIC ENGINE] Successfully downloaded and cached '{style_key}' to {local_path} ({file_size} bytes)")
        return local_path
    except Exception as e:
        print(f"[MUSIC ENGINE ERROR] Failed to download background music: {e}", file=sys.stderr)
        # Clean up partial download if any
        if os.path.exists(local_path):
            try:
                os.remove(local_path)
            except:
                pass
        return None
