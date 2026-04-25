import os
import random
import google.generativeai as genai
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# Configure Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

model = genai.GenerativeModel("gemini-3-flash-preview")

MAX_SCRIPT_WORDS = 120

# Bad prefixes for cleaning (case-insensitive)
BAD_PREFIXES = ("here", "this", "note", "format", "example", "sure", "okay")


def generate_fallback_script(topic: str) -> str:
    """Generate viral fallback script when Gemini fails."""
    return f"""I wish I never ignored this...
It started with {topic}
Everything felt normal
Until one small thing changed
And I couldn't stop it anymore
Now I regret everything"""


def trim_to_word_limit(text: str, max_words: int = 120) -> str:
    """Trim text to max word limit."""
    words = text.split()
    if len(words) > max_words:
        print(f"[SCRIPT] Trimming from {len(words)} to {max_words} words")
        return " ".join(words[:max_words])
    return text


def call_gemini(prompt: str, retries: int = 2) -> str:
    """Call Gemini API with retry logic."""
    for attempt in range(retries):
        try:
            print(f"[GEMINI] Attempt {attempt + 1}/{retries}...")
            response = model.generate_content(prompt)
            print(f"[GEMINI] Success, response length: {len(response.text.strip())} chars")
            return response.text
        except Exception as e:
            error_str = str(e)
            print(f"[GEMINI] Attempt {attempt + 1} failed: {error_str[:100]}")
            if attempt == retries - 1:
                raise e
    return ""


def clean_script(text: str) -> str:
    """Clean Gemini output - remove garbage formatting."""
    lines = text.split("\n")
    lines = [l.strip() for l in lines if l.strip()]
    cleaned = []
    for line in lines[:20]:
        # Remove markdown markers
        line = line.replace("**", "").replace("*", "")
        line = line.replace('"', "")
        # Case-insensitive prefix check
        if line and not any(line.lower().startswith(p) for p in BAD_PREFIXES):
            cleaned.append(line)
    return "\n".join(cleaned)


def generate_script(topic: str) -> str:
    """Generate viral short-form video script from topic (single API call).
    
    Args:
        topic: Topic for the video
        
    Returns:
        Clean viral script with hook, story, retention
    """
    if not GEMINI_API_KEY:
        print(f"[GEMINI] SKIP: No API key configured")
        return generate_fallback_script(topic)

    prompt = f"""Write a VIRAL short-form video script.

Topic: {topic}

STYLE:
- Reddit confession tone
- First person storytelling
- Emotional twist at end

RULES:
- Max 120 words
- Strong hook in first line
- Short punchy lines
- Each line = caption style
- No explanations, only script

Generate now:"""

    try:
        raw = call_gemini(prompt, retries=2)
        cleaned = clean_script(raw)
        return trim_to_word_limit(cleaned, MAX_SCRIPT_WORDS)
    except Exception as e:
        print(f"[SCRIPT ERROR] {e}")
        return generate_fallback_script(topic)
