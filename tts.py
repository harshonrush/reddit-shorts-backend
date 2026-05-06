import os
import base64
import requests
from elevenlabs.client import ElevenLabs

client = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))

# Gemini TTS configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_TTS_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateAudio"


def generate_audio_gemini(text: str, output_path: str) -> str:
    """Generate TTS using Gemini 2.5 Flash as fallback.
    
    Args:
        text: The script text to convert
        output_path: Path to save the audio file (.mp3)
        
    Returns:
        Path to the generated audio file
    """
    if not GEMINI_API_KEY:
        raise Exception("GEMINI_API_KEY not set")
    
    print(f"[GEMINI TTS] Generating audio...", file=os.sys.stderr)
    
    url = f"{GEMINI_TTS_URL}?key={GEMINI_API_KEY}"
    
    payload = {
        "text": text,
        "outputAudioFormat": "mp3"
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    
    response = requests.post(url, json=payload, headers=headers, timeout=60)
    response.raise_for_status()
    
    result = response.json()
    
    # Gemini returns base64-encoded audio
    audio_base64 = result.get("audioContent", "")
    if not audio_base64:
        raise Exception("No audio content in Gemini response")
    
    # Decode and save
    audio_bytes = base64.b64decode(audio_base64)
    with open(output_path, "wb") as f:
        f.write(audio_bytes)
    
    print(f"[GEMINI TTS] Audio saved to {output_path}", file=os.sys.stderr)
    return output_path


def generate_audio(text: str, output_path: str, voice_id: str = None) -> str:
    """Generate TTS using ElevenLabs with Gemini fallback.
    
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
    
    # Try ElevenLabs first
    try:
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
        
    except Exception as e:
        print(f"[ELEVENLABS ERROR] {e}, falling back to Gemini TTS...", file=os.sys.stderr)
        
        # Fallback to Gemini TTS
        try:
            return generate_audio_gemini(clean_text, output_path)
        except Exception as gemini_error:
            print(f"[GEMINI TTS ERROR] {gemini_error}", file=os.sys.stderr)
            raise Exception(f"Both TTS services failed: ElevenLabs({e}), Gemini({gemini_error})")
