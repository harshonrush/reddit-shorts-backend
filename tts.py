import os
from elevenlabs.client import ElevenLabs

client = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))


def generate_audio(text: str, output_path: str, voice_id: str = None) -> str:
    """Generate TTS using ElevenLabs (NEW SDK).
    
    Args:
        text: The script text to convert
        output_path: Path to save the audio file (.mp3)
        voice_id: ElevenLabs voice ID (default: Adam)
        
    Returns:
        Path to the generated audio file
    """
    # Clean up text
    clean_text = text.replace("HOOK:", "").replace("SCRIPT:", "")
    clean_text = " ".join(clean_text.split())
    
    # Default voice: Adam (male_deep)
    if not voice_id:
        voice_id = "pNInz6obpgDQGcFmaJgB"
    
    print(f"[ELEVENLABS] Generating audio with voice {voice_id}...", file=os.sys.stderr)

    # NEW SDK: client.text_to_speech.convert (streaming)
    audio = client.text_to_speech.convert(
        voice_id=voice_id,
        model_id="eleven_flash_v2_5",
        text=clean_text
    )

    # Save streamed audio
    with open(output_path, "wb") as f:
        for chunk in audio:
            f.write(chunk)

    print(f"[ELEVENLABS] Audio saved to {output_path}", file=os.sys.stderr)
    return output_path
