import os
from elevenlabs import generate, save, set_api_key

# Initialize ElevenLabs API
set_api_key(os.getenv("ELEVENLABS_API_KEY"))


def generate_audio(text: str, output_path: str) -> str:
    """Convert script text to speech using ElevenLabs (single API call for speed).
    
    Args:
        text: The script text to convert
        output_path: Path to save the audio file (.mp3)
        
    Returns:
        Path to the generated audio file
    """
    # Clean up text
    clean_text = text.replace("HOOK:", "").replace("SCRIPT:", "")
    clean_text = " ".join(clean_text.split())
    
    print(f"[ELEVENLABS] Generating audio (single call)...", file=os.sys.stderr)
    
    # Generate audio in single call (faster, cheaper)
    audio = generate(
        text=clean_text,
        voice="Adam",  # or Rachel, Antoni, etc.
        model="eleven_multilingual_v2"
    )
    
    save(audio, output_path)
    
    print(f"[ELEVENLABS] Audio saved to {output_path}", file=os.sys.stderr)
    
    return output_path
