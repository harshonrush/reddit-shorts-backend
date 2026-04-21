from gtts import gTTS
import os


def generate_audio(text: str, output_path: str) -> str:
    """Convert script text to speech using gTTS.
    
    Args:
        text: The script text to convert
        output_path: Path to save the audio file (.mp3)
        
    Returns:
        Path to the generated audio file
    """
    # Clean up text for TTS
    # Remove common script markers
    clean_text = text.replace("HOOK:", "").replace("SCRIPT:", "")
    clean_text = " ".join(clean_text.split())  # Normalize whitespace
    
    # Generate audio with gTTS (English, normal speed)
    tts = gTTS(text=clean_text, lang='en', slow=False)
    tts.save(output_path)
    
    return output_path
