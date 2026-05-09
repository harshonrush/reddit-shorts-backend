"""Shared constants and configuration for the Reddit Shorts backend."""

# Voice mapping (user-friendly names → ElevenLabs voice IDs)
VOICE_MAP = {
    "male_deep": "29vD33N1CtxCmqQRPOHJ",
    "male_calm": "0JRpJnrcyEVIabsZ4U5I",
    "female_energetic": "AZnzlk1XvdvUeBnXmlld",
    "female_soft": "TYKLc7ViOIGE13dSZYlK",
}

# Gemini voice fallback mapping (ElevenLabs ID → Gemini voice name)
GEMINI_VOICE_MAP = {
    "29vD33N1CtxCmqQRPOHJ": "Kore",       # male_deep
    "0JRpJnrcyEVIabsZ4U5I": "Aoede",      # male_calm
    "AZnzlk1XvdvUeBnXmlld": "Puck",       # female_energetic
    "TYKLc7ViOIGE13dSZYlK": "Charon",     # female_soft
}

# Language prompts for script generation
LANGUAGE_PROMPTS = {
    "english": "Generate in English",
    "hindi": "Generate in Hindi language using Devanagari script",
}

# Niche-based topic mapping
NICHE_TOPICS = {
    "facts": ["amazing facts", "did you know", "mind blowing facts", "science facts", "history facts"],
    "motivation": ["discipline", "morning routine", "success mindset", "never give up", "transformation"],
    "reddit_stories": ["creepy encounter", "strange neighbor", "mystery solved", "unexpected twist", "life changing moment"],
    "ai_stories": ["futuristic story", "AI takeover", "robot romance", "virtual reality", "digital consciousness"],
    "history": ["ancient mysteries", "war stories", "forgotten history", "historical figures", "empire rise and fall"],
    "heartbreak": ["heartbreak", "breakup recovery", "moving on", "lost love", "emotional healing"],
    "business": ["startup struggle", "entrepreneur journey", "side hustle success", "business betrayal", "rags to riches"],
    "fitness": ["gym discipline", "weight loss journey", "fitness transformation", "mental strength", "health wake-up call"],
    "stories": ["creepy encounter", "strange neighbor", "mystery solved", "unexpected twist", "life changing moment"],
}

# Default random topics (backward compat)
DEFAULT_TOPICS = [
    "heartbreak",
    "cheating",
    "toxic parents",
    "revenge",
    "betrayal",
    "friendship gone wrong",
    "workplace drama",
    "family secrets",
]
