"""Generate scene-specific image prompts using Gemini AI."""
import os
import re
import sys
import google.generativeai as genai
from typing import List, Dict
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

model = genai.GenerativeModel("gemini-2.5-flash")


def _split_script_into_scenes(script: str, max_scenes: int = 5) -> List[str]:
    """Split script into logical scenes/segments.
    
    Args:
        script: The full video script
        max_scenes: Maximum number of scenes to generate
        
    Returns:
        List of scene descriptions
    """
    # Split by sentences
    sentences = re.split(r'[.!?]+', script)
    sentences = [s.strip() for s in sentences if s.strip()]
    
    if len(sentences) <= max_scenes:
        return sentences
    
    # Group sentences into chunks
    scenes_per_chunk = len(sentences) // max_scenes
    scenes = []
    for i in range(0, len(sentences), scenes_per_chunk):
        chunk = " ".join(sentences[i:i + scenes_per_chunk])
        if chunk.strip():
            scenes.append(chunk)
    
    return scenes[:max_scenes]


def generate_image_prompts(script: str, niche: str = "general") -> List[Dict]:
    """Generate image prompts for each scene using Gemini.
    
    Args:
        script: The video script
        niche: The video niche (facts, horror, story, etc.)
        
    Returns:
        List of dicts with scene text and image prompts
    """
    scenes = _split_script_into_scenes(script)
    
    print(f"[IMAGE PROMPTS] Generating prompts for {len(scenes)} scenes", file=sys.stderr)
    
    results = []
    
    for idx, scene in enumerate(scenes, 1):
        print(f"[IMAGE PROMPTS] Scene {idx}/{len(scenes)}: {scene[:50]}...", file=sys.stderr)
        
        # Create prompt for Gemini
        system_prompt = f"""You are an expert at creating detailed, cinematic image prompts for short-form videos.
        
Given a scene from a {niche} video, generate a vivid image prompt that:
1. Is highly visual and cinematic
2. Works well for AI image generation
3. Captures the mood and emotion of the scene
4. Suggests specific visual style (cinematic, dramatic, etc.)
5. Is concise (under 100 words)

Format your response as just the image prompt, no other text."""
        
        try:
            response = model.generate_content(
                f"{system_prompt}\n\nScene: {scene}",
                generation_config=genai.types.GenerationConfig(
                    temperature=0.7,
                    max_output_tokens=150
                )
            )
            
            prompt_text = response.text.strip()
            print(f"[IMAGE PROMPTS] Generated: {prompt_text[:60]}...", file=sys.stderr)
            
            results.append({
                "scene_text": scene,
                "image_prompt": prompt_text,
                "niche": niche
            })
        
        except Exception as e:
            print(f"[IMAGE PROMPTS] Error generating prompt: {e}", file=sys.stderr)
            # Fallback: create a simple prompt from the scene
            fallback_prompt = f"Cinematic {niche} scene: {scene[:80]}"
            results.append({
                "scene_text": scene,
                "image_prompt": fallback_prompt,
                "niche": niche
            })
    
    return results


def generate_batch_image_prompts(scripts: List[str], niche: str = "general") -> List[List[Dict]]:
    """Generate image prompts for multiple scripts.
    
    Args:
        scripts: List of video scripts
        niche: The video niche
        
    Returns:
        List of prompt lists (one per script)
    """
    results = []
    for script in scripts:
        prompts = generate_image_prompts(script, niche)
        results.append(prompts)
    
    return results
