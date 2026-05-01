"""FFmpeg-based viral captions with big text, background box, and zoom effects."""
import os
import subprocess
import sys
from typing import List, Dict


def escape_text(text: str) -> str:
    """Escape text for FFmpeg drawtext."""
    return (
        text.replace("\\", "\\\\")
            .replace(":", "\\:")
            .replace("'", "\\'")
            .replace(",", "\\,")
            .replace("%", "\\%")
            .replace("\n", " ")
    )


def generate_viral_captions_ffmpeg(
    video_path: str,
    audio_path: str,
    words: List[Dict],
    output_path: str
):
    """Generate viral-style video with FFmpeg drawtext overlays.
    
    Features:
    - Big bold white text with black stroke
    - Background box for readability
    - Zoom effect on highlighted words
    - Center-bottom positioning
    """
    
    if not words:
        # No captions, just copy video
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", audio_path,
            "-c:v", "libx264", "-preset", "fast",
            "-c:a", "aac",
            "-shortest",
            output_path
        ]
        subprocess.run(cmd, check=True)
        return output_path
    
    # Build drawtext filters for each word
    # Format: word with start/end times, zoom effect
    filters = []
    
    # Group words into lines (max 4 words per line for mobile)
    max_per_line = 4
    lines = []
    current_line = []
    
    for word in words:
        current_line.append(word)
        if len(current_line) >= max_per_line or word["word"].endswith((".", "!", "?")):
            lines.append(current_line)
            current_line = []
    
    if current_line:
        lines.append(current_line)
    
    # Generate drawtext for each line with word highlighting
    base_y = 1600  # Bottom position for 1920px height
    
    for line_idx, line_words in enumerate(lines):
        line_start = line_words[0]["start"]
        line_end = line_words[-1]["end"]
        
        # Build text with individual word styling
        line_text = " ".join(w["word"] for w in line_words)
        safe_text = escape_text(line_text)
        
        # Calculate center X position (approximate)
        # Each char ~40px at 80pt font
        text_width = len(line_text) * 40
        x_pos = f"(w-text_w)/2"  # Center horizontally
        y_pos = base_y - (len(lines) - line_idx - 1) * 100  # Stack lines
        
        # Drawtext filter with big bold styling
        # Font: Arial Bold, 80pt, white with black stroke
        drawtext = (
            f"drawtext=fontfile=/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf:"
            f"text='{safe_text}':"
            f"fontsize=80:"
            f"fontcolor=white:"
            f"borderw=4:bordercolor=black:"
            f"x={x_pos}:y={y_pos}:"
            f"enable='between(t,{line_start},{line_end})'"
        )
        
        filters.append(drawtext)
    
    # Build FFmpeg command
    filter_complex = ",".join(filters) if filters else "null"
    
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", audio_path,
        "-filter_complex", f"[0:v]{filter_complex}[v]",
        "-map", "[v]",
        "-map", "1:a",
        "-c:v", "libx264", "-preset", "fast",
        "-c:a", "aac",
        "-shortest",
        output_path
    ]
    
    print(f"[FFMPEG] Running: {' '.join(cmd)}", file=sys.stderr)
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"[FFMPEG ERROR FULL]\n{result.stderr}", file=sys.stderr)
        raise RuntimeError(f"FFmpeg failed: {result.stderr}")
    
    print(f"[FFMPEG] Viral captions added: {output_path}", file=sys.stderr)
    return output_path


def generate_animated_captions(
    video_path: str,
    audio_path: str,
    words: List[Dict],
    output_path: str
):
    """Generate animated captions with zoom effect on current word."""
    
    if not words:
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", audio_path,
            "-c:v", "libx264", "-preset", "fast",
            "-c:a", "aac",
            "-shortest",
            output_path
        ]
        subprocess.run(cmd, check=True)
        return output_path
    
    # Build complex filter with per-word animations
    filter_parts = []
    
    # Group into lines
    max_per_line = 4
    lines = []
    current_line = []
    
    for word in words:
        current_line.append(word)
        if len(current_line) >= max_per_line or word["word"].endswith((".", "!", "?")):
            lines.append(current_line)
            current_line = []
    
    if current_line:
        lines.append(current_line)
    
    base_y = 1700  # Near bottom for 9:16
    
    # Create drawtext for each word with zoom effect when active
    for line_idx, line_words in enumerate(lines):
        line_text = " ".join(w["word"] for w in line_words)
        safe_line_text = escape_text(line_text)
        
        # Calculate position
        y_pos = base_y - (len(lines) - line_idx - 1) * 90
        
        # Base text (all words visible, but smaller/inactive)
        base_filter = (
            f"drawtext=fontfile=/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf:"
            f"text='{safe_line_text}':"
            f"fontsize=72:"
            f"fontcolor=gray@0.6:"
            f"borderw=3:bordercolor=black@0.8:"
            f"x=(w-text_w)/2:y={y_pos}:"
            f"enable='between(t,{line_words[0]['start']},{line_words[-1]['end']})'"
        )
        
        filter_parts.append(base_filter)
        
        # Highlighted word (zoom effect)
        for i, word in enumerate(line_words):
            word_start = word["start"]
            word_end = word["end"]
            
            # Calculate X position for this word
            prefix = " ".join(w["word"] for w in line_words[:i])
            prefix_width = len(prefix) * 35 if prefix else 0
            
            # Escape word text for FFmpeg
            safe_word = escape_text(word['word'])
            
            # Highlight: larger fixed fontsize (no animation to avoid FFmpeg parsing issues)
            highlight_filter = (
                f"drawtext=fontfile=/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf:"
                f"text='{safe_word}':"
                f"fontsize=84:"
                f"fontcolor=yellow:"
                f"borderw=4:bordercolor=black:"
                f"x=(w-text_w)/2+{prefix_width}:y={y_pos}:"
                f"enable='between(t,{word_start},{word_end})'"
            )
            
            filter_parts.append(highlight_filter)
    
    # Apply all filters
    filter_complex = ",".join(filter_parts) if filter_parts else "null"
    
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", audio_path,
        "-filter_complex", f"[0:v]{filter_complex}[v]",
        "-map", "[v]",
        "-map", "1:a",
        "-c:v", "libx264", "-preset", "fast",
        "-c:a", "aac",
        "-shortest",
        output_path
    ]
    
    print(f"[FFMPEG] Generating animated captions...", file=sys.stderr)
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"[FFMPEG ERROR FULL]\n{result.stderr}", file=sys.stderr)
        raise RuntimeError(f"FFmpeg failed: {result.stderr}")
    
    print(f"[FFMPEG] Animated captions complete: {output_path}", file=sys.stderr)
    return output_path
