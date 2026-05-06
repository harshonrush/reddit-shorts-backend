import os
import base64
import wave
from elevenlabs.client import ElevenLabs

client = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))

# Gemini TTS configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


def generate_audio_gemini(text: str, output_path: str, voice_name: str = "Kore") -> str:
    """Generate TTS using Gemini Flash TTS as fallback.
    
    Args:
        text: The script text to convert
        output_path: Path to save the audio file (.wav)
        voice_name: Voice name (Kore, Aoede, etc.)
        
    Returns:
        Path to the generated audio file
    """
    if not GEMINI_API_KEY:
        raise Exception("GEMINI_API_KEY not set")
    
    print(f"[GEMINI TTS] Generating audio with voice {voice_name}...", file=os.sys.stderr)
    
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        raise Exception("google-genai package not installed. Run: pip install google-genai")
    
    gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    
    response = gemini_client.models.generate_content(
        model="gemini-2.5-flash-preview-tts",
        contents=text,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=voice_name,
                    )
                )
            ),
        )
    )
    
    # Extract audio data
    if not response.candidates:
        raise Exception("No candidates in Gemini response")
    
    parts = response.candidates[0].content.parts
    if not parts or not parts[0].inline_data:
        raise Exception("No audio data in Gemini response")
    
    audio_data = parts[0].inline_data.data
    
    # Save as WAV (Gemini returns PCM audio)
    # Convert to MP3 if needed, or save as WAV
    if output_path.endswith('.mp3'):
        # Save as WAV first, then convert
        wav_path = output_path.replace('.mp3', '.wav')
    else:
        wav_path = output_path
    
    # Save PCM as WAV file (24kHz, 16-bit, mono)
    with wave.open(wav_path, "wb") as wf:
        wf.setnchannels(1)  # mono
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(24000)  # 24kHz
        wf.writeframes(audio_data)
    
    # Convert to MP3 if needed
    if output_path.endswith('.mp3'):
        try:
            import subprocess
            subprocess.run([
                "ffmpeg", "-y", "-i", wav_path,
                "-codec:a", "libmp3lame", "-q:a", "2",
                output_path
            ], capture_output=True, check=True)
            os.remove(wav_path)  # Clean up temp WAV
        except Exception as e:
            print(f"[GEMINI TTS] MP3 conversion failed: {e}, using WAV", file=os.sys.stderr)
            # Rename WAV to expected path
            os.rename(wav_path, output_path.replace('.mp3', '.wav'))
            return output_path.replace('.mp3', '.wav')
    
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
        
        # Fallback to Gemini TTS with mapped voice
        # Map ElevenLabs voice to Gemini voice
        GEMINI_VOICE_MAP = {
            "29vD33N1CtxCmqQRPOHJ": "Kore",      # male_deep -> Kore
            "0JRpJnrcyEVIabsZ4U5I": "Aoede",     # male_calm -> Aoede  
            "AZnzlk1XvdvUeBnXmlld": "Puck",     # female_energetic -> Puck
            "TYKLc7ViOIGE13dSZYlK": "Charon",   # female_soft -> Charon
        }
        gemini_voice = GEMINI_VOICE_MAP.get(voice_id, "Kore")
        
        try:
            return generate_audio_gemini(clean_text, output_path, voice_name=gemini_voice)
        except Exception as gemini_error:
            print(f"[GEMINI TTS ERROR] {gemini_error}", file=os.sys.stderr)
            raise Exception(f"Both TTS services failed: ElevenLabs({e}), Gemini({gemini_error})")
