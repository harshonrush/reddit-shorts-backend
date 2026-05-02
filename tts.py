import os
from elevenlabs.client import ElevenLabs

client = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))


def generate_audio(text: str, output_path: str) -> str:
    """Generate TTS using ElevenLabs (NEW SDK).
    
    Args:
        text: The script text to convert
        output_path: Path to save the audio file (.mp3)
        
    Returns:
        Path to the generated audio file
    """
    # Clean up text
    clean_text = text.replace("HOOK:", "").replace("SCRIPT:", "")
    clean_text = " ".join(clean_text.split())
    
    print(f"[ELEVENLABS] Generating audio...", file=os.sys.stderr)

    # NEW SDK: client.text_to_speech.convert (streaming)
    audio = client.text_to_speech.convert(
        voice_id="pNInz6obpgDQGcFmaJgB",  # Adam voice
        model_id="eleven_flash_v2.5",
        text=clean_text
    )

    # Save streamed audio
    with open(output_path, "wb") as f:
        for chunk in audio:
            f.write(chunk)

    print(f"[ELEVENLABS] Audio saved to {output_path}", file=os.sys.stderr)
    return output_path
