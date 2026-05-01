import re
import math
import os
import requests
import sys
from datetime import timedelta

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")

# Constants
SECONDS_PER_LINE = 2.0  # Basic timing: 2 seconds per subtitle line
MAX_WORDS_PER_LINE = 8  # Max words per subtitle line


def format_srt_time(seconds: float) -> str:
    """Format seconds as SRT timestamp (HH:MM:SS,mmm)."""
    td = timedelta(seconds=seconds)
    hours, remainder = divmod(td.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    milliseconds = int((seconds % 1) * 1000)
    seconds = int(seconds)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def split_script_into_lines(script: str, max_words: int = MAX_WORDS_PER_LINE) -> list:
    """Split script into lines with max words per line."""
    # Clean up script text
    # Remove common markers
    script = script.replace("HOOK:", "").replace("SCRIPT:", "")
    
    # Split into sentences/phrases
    words = script.split()
    lines = []
    current_line = []
    
    for word in words:
        current_line.append(word)
        # Break line if max words reached or sentence ends
        if len(current_line) >= max_words or word.endswith(('.', '!', '?')):
            lines.append(" ".join(current_line))
            current_line = []
    
    # Add remaining words
    if current_line:
        lines.append(" ".join(current_line))
    
    return lines


def generate_srt(script: str, output_path: str) -> str:
    """Generate SRT subtitle file from script.
    
    Args:
        script: The video script text
        output_path: Path to save .srt file
        
    Returns:
        Path to generated SRT file
    """
    lines = split_script_into_lines(script)
    
    srt_entries = []
    current_time = 0.0
    
    for i, line in enumerate(lines, start=1):
        # Calculate timing
        start_time = current_time
        end_time = current_time + SECONDS_PER_LINE
        
        # Format entry
        entry = f"{i}\n"
        entry += f"{format_srt_time(start_time)} --> {format_srt_time(end_time)}\n"
        entry += f"{line}\n"
        
        srt_entries.append(entry)
        current_time = end_time
    
    # Write SRT file
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(srt_entries))
    
    return output_path


# ============ DEEPGRAM VIRAL CAPTIONS ============

def get_word_timestamps(audio_path: str):
    """Get word-level timestamps from Deepgram API."""
    if not DEEPGRAM_API_KEY:
        raise RuntimeError("DEEPGRAM_API_KEY not set")

    url = "https://api.deepgram.com/v1/listen"

    with open(audio_path, "rb") as f:
        res = requests.post(
            url,
            headers={"Authorization": f"Token {DEEPGRAM_API_KEY}"},
            files={"file": f},
            params={"punctuate": "true", "utterances": "false"}
        )

    data = res.json()

    # Extract word timestamps
    words = []
    for result in data.get("results", {}).get("channels", []):
        for alt in result.get("alternatives", []):
            for word in alt.get("words", []):
                words.append({
                    "word": word["word"],
                    "start": word["start"],
                    "end": word["end"],
                    "confidence": word.get("confidence", 1.0)
                })

    return words


def format_ass_time(seconds: float) -> str:
    """Format seconds as ASS timestamp (H:MM:SS.cc)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    centis = int((secs % 1) * 100)
    secs = int(secs)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"


def generate_viral_ass(words: list, output_path: str):
    """Generate viral-style ASS subtitles with karaoke highlighting."""
    # ASS Header with viral styling - white text, yellow highlight, bold, centered
    ass = """[Script Info]
Title: Viral Captions
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
Timer: 100.0000

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,72,&H00FFFFFF,&H0000FFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,3,4,0,2,30,30,250,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    if not words:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(ass)
        return output_path

    # Group words into lines (max 5 words per line for mobile)
    max_words_per_line = 5
    lines = []
    current_line = []

    for word in words:
        current_line.append(word)
        if len(current_line) >= max_words_per_line or word["word"].endswith((".", "!", "?")):
            lines.append(current_line)
            current_line = []

    if current_line:
        lines.append(current_line)

    # Generate karaoke-style captions
    for line_words in lines:
        line_start = line_words[0]["start"]
        line_end = line_words[-1]["end"]

        # Build text with karaoke timing codes
        text_parts = []
        for i, word in enumerate(line_words):
            word_text = word["word"]
            # ASS karaoke tag: {\k<duration>}word
            duration_cs = int((word["end"] - word["start"]) * 100)
            text_parts.append(f"{{\\k{duration_cs}}}{word_text}")

        text = " ".join(text_parts)

        # Add dialogue line
        start_str = format_ass_time(line_start)
        end_str = format_ass_time(line_end)

        ass += f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{text}\\n"

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(ass)

    print(f"[DEEPGRAM] Generated ASS with {len(words)} words", file=sys.stderr)
    return output_path


def generate_captions(audio_path: str, output_path: str):
    """Full pipeline: Deepgram -> word timestamps -> viral ASS."""
    print(f"[DEEPGRAM] Transcribing audio: {audio_path}", file=sys.stderr)
    words = get_word_timestamps(audio_path)
    print(f"[DEEPGRAM] Got {len(words)} words with timestamps", file=sys.stderr)
    return generate_viral_ass(words, output_path)
