import re
import math
from datetime import timedelta

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
