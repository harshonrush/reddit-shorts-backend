"""Fetch images from Pexels API based on prompts."""
import os
import sys
import requests
import json
from typing import List, Dict, Optional
from urllib.parse import quote
from dotenv import load_dotenv

load_dotenv()

PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")
PEXELS_BASE_URL = "https://api.pexels.com/v1"


def search_images(query: str, per_page: int = 5) -> List[Dict]:
    """Search images on Pexels.
    
    Args:
        query: Search query (image prompt)
        per_page: Number of results to return
        
    Returns:
        List of image dicts with 'url', 'width', 'height', 'photographer'
    """
    
    if not PEXELS_API_KEY:
        print("[PEXELS] No API key found, skipping image fetch", file=sys.stderr)
        return []
    
    url = f"{PEXELS_BASE_URL}/search"
    headers = {"Authorization": PEXELS_API_KEY}
    params = {
        "query": query,
        "per_page": per_page,
        "orientation": "portrait"  # Vertical for shorts
    }
    
    try:
        print(f"[PEXELS] Searching: {query}", file=sys.stderr)
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        photos = data.get("photos", [])
        
        results = []
        for photo in photos:
            results.append({
                "url": photo["src"]["original"],  # Largest resolution
                "width": photo["width"],
                "height": photo["height"],
                "photographer": photo.get("photographer", "Unknown"),
                "photographer_url": photo.get("photographer_url", "")
            })
        
        print(f"[PEXELS] Found {len(results)} images", file=sys.stderr)
        return results
    
    except requests.exceptions.RequestException as e:
        print(f"[PEXELS] Request failed: {e}", file=sys.stderr)
        return []


def download_image(image_url: str, output_path: str) -> bool:
    """Download image from URL to local path.
    
    Args:
        image_url: URL of the image
        output_path: Local path to save image
        
    Returns:
        True if successful, False otherwise
    """
    try:
        print(f"[PEXELS] Downloading image to {output_path}", file=sys.stderr)
        response = requests.get(image_url, timeout=30)
        response.raise_for_status()
        
        with open(output_path, 'wb') as f:
            f.write(response.content)
        
        file_size = os.path.getsize(output_path)
        print(f"[PEXELS] Downloaded {file_size} bytes", file=sys.stderr)
        return True
    
    except Exception as e:
        print(f"[PEXELS] Download failed: {e}", file=sys.stderr)
        return False


def fetch_best_image(image_prompt: str, output_path: str, fallback_query: str = None) -> Optional[str]:
    """Fetch best image for a prompt, with fallback.
    
    Args:
        image_prompt: Detailed image description from Gemini
        output_path: Where to save the image
        fallback_query: Fallback search term if primary search fails
        
    Returns:
        Path to downloaded image, or None if failed
    """
    
    # Try main prompt first
    images = search_images(image_prompt, per_page=3)
    
    if not images and fallback_query:
        print(f"[PEXELS] No results for '{image_prompt}', trying fallback: {fallback_query}", file=sys.stderr)
        images = search_images(fallback_query, per_page=3)
    
    if not images:
        print(f"[PEXELS] No images found for '{image_prompt}'", file=sys.stderr)
        return None
    
    # Use first result (highest relevance)
    best_image = images[0]
    success = download_image(best_image["url"], output_path)
    
    if success:
        return output_path
    else:
        return None


def fetch_images_for_scenes(
    scene_prompts: List[Dict],
    output_dir: str,
    fallback_niche: str = "nature"
) -> List[Dict]:
    """Fetch images for multiple scenes.
    
    Args:
        scene_prompts: List of scene dicts with 'image_prompt' key
        output_dir: Directory to save images
        fallback_niche: Fallback search term if specific prompt fails
        
    Returns:
        List of dicts with scene info and image paths (None if fetch failed)
    """
    
    os.makedirs(output_dir, exist_ok=True)
    results = []
    
    for idx, scene in enumerate(scene_prompts, 1):
        image_prompt = scene.get("image_prompt", "")
        
        # Extract first few words as fallback query
        fallback = " ".join(image_prompt.split()[:3]) if image_prompt else fallback_niche
        
        output_path = os.path.join(output_dir, f"scene_{idx:02d}.jpg")
        
        try:
            image_path = fetch_best_image(image_prompt, output_path, fallback_query=fallback)
            results.append({
                "scene_index": idx,
                "image_prompt": image_prompt,
                "image_path": image_path,
                "status": "success" if image_path else "failed"
            })
        except Exception as e:
            print(f"[PEXELS] Error fetching scene {idx}: {e}", file=sys.stderr)
            results.append({
                "scene_index": idx,
                "image_prompt": image_prompt,
                "image_path": None,
                "status": "error"
            })
    
    print(f"[PEXELS] Fetched {sum(1 for r in results if r['status'] == 'success')}/{len(results)} images", file=sys.stderr)
    return results
