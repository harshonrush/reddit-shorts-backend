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

# Fallback templates when quota exceeded
FALLBACK_TEMPLATES = [
    """I never saw this coming...
It started as a normal day
Then everything changed
Now I can't go back
This is what happened""",
    """They said it was impossible
But I proved them wrong
Against all odds
I made it happen
Here's the truth""",
    """I wish I knew this sooner
Would have saved me years
The secret nobody talks about
Until now
Listen carefully""",
    """My biggest mistake
Cost me everything
Don't let this happen to you
Learn from my error
This changed my life""",
    """Nobody believed me
When I told them
Now they see the proof
Right before their eyes
I was right all along""",
]

FALLBACK_TOPICS = [
    "betrayal", "unexpected success", "hidden truth", "second chance",
    "toxic friend", "secret wealth", "career change", "family secret",
    "wrong accusation", "miracle recovery"
]


def generate_story(topic: str) -> str:
    """Generate viral Reddit-style story with strong hook."""
    if not GEMINI_API_KEY:
        # Fallback for testing
        return f"I never thought {topic} would change everything. But it did."
    
    try:
        prompt = f"""Write an emotional, engaging Reddit-style story about {topic}. 
Make it sound authentic and viral-worthy.
- Strong emotional hook in the opening
- Relatable situation with clear emotional arc
- Natural, conversational language
- Around 100-150 words total
- No titles or formatting, just the story"""
        
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        if "429" in str(e) or "quota" in str(e).lower() or "RESOURCE_EXHAUSTED" in str(e):
            print(f"[SCRIPT] Gemini quota exceeded, using fallback story for: {topic}")
            return f"I never expected {topic} to affect me like this. What I discovered changed everything I thought I knew."
        raise


def generate_script(topic_or_story: str) -> str:
    """Generate viral short-form video script.
    
    Args:
        topic_or_story: Topic or pre-generated story
        
    Returns:
        Clean viral script with hook, story, retention
    """
    if not GEMINI_API_KEY:
        # Fallback mock script
        return random.choice(FALLBACK_TEMPLATES)
    
    try:
        prompt = f"""You are writing a VIRAL short-form video script for reels.

Topic: {topic_or_story}

RULES:
- Max 120 words
- Start with a strong HOOK in first line
- Format like a conversation / story
- Emotional, dramatic, relatable
- Use short sentences
- Add suspense and curiosity
- Each line should feel like caption text
- No long paragraphs
- No explanations

FORMAT:
Line 1: Hook
Then story unfolds line by line

Example tone:
"I wasn't supposed to see this..."
"My mom called me at 2AM..."
"I trusted him... worst mistake"

Now generate:"""
        
        response = model.generate_content(prompt)
        return clean_script(response.text)
    except Exception as e:
        if "429" in str(e) or "quota" in str(e).lower() or "RESOURCE_EXHAUSTED" in str(e):
            print(f"[SCRIPT] Gemini quota exceeded, using fallback template")
            return random.choice(FALLBACK_TEMPLATES)
        raise


def clean_script(text: str) -> str:
    """Clean Gemini output - remove garbage formatting."""
    lines = text.split("\n")
    lines = [l.strip() for l in lines if l.strip()]
    # Remove markdown and limit to 20 lines
    cleaned = []
    for line in lines[:20]:
        # Remove markdown markers
        line = line.replace("**", "").replace("*", "")
        line = line.replace('"', "")
        if line and not line.startswith(("Here", "This", "Note:", "Format:", "Example")):
            cleaned.append(line)
    return "\n".join(cleaned)
