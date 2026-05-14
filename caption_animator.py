"""Word-by-word animated captions using FFmpeg drawtext filter."""
import os
import subprocess
import sys
import tempfile
import json
from typing import List, Dict, Tuple


def _format_time_ms(seconds: float) -> str:
    """Format seconds to FFmpeg time format (HH:MM:SS.mmm)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"


def _clamp_position(value: float, min_val: float, max_val: float) -> float:
    """Clamp value between min and max."""
    return max(min_val, min(max_val, value))


def _generate_drawtext_filter(words: List[Dict], video_width: int = 360, video_height: int = 640) -> str:
    """Generate FFmpeg drawtext filter for word-by-word animation.
    
    Features:
    - Each word fades in and out
    - Optional pop/zoom effect
    - Centered positioning
    - Large, bold font for viral look
    
    Args:
        words: List of dicts with 'word', 'start', 'end' keys
        video_width: Video width (default 360 for shorts)
        video_height: Video height (default 640 for shorts)
        
    Returns:
        FFmpeg filter string for drawtext
    """
    if not words:
        return "scale=360:640"
    
    # Create multiple drawtext filters, one per word
    filters = []
    
    # Font settings
    font_size = 60
    font_name = "DejaVu-Sans-Bold"
    text_color = "white"
    outline_color = "black"
    
    for idx, word_data in enumerate(words):
        word = word_data["word"].strip()
        if not word:
            continue
        
        start_time = word_data["start"]
        end_time = word_data["end"]
        
        # Animation: fade in (0.1s), hold, fade out (0.1s)
        fade_in = 0.1
        fade_out = 0.1
        hold_start = start_time + fade_in
        hold_end = end_time - fade_out
        
        # Calculate opacity at each phase
        # Format: enable='between(t,START,END)'
        enable_expr = f"between(t,{start_time},{end_time})"
        
        # Alpha animation for fade effect
        # At start: alpha goes from 0 to 1 in fade_in seconds
        # Then holds at 1
        # Then fades from 1 to 0 in fade_out seconds
        alpha_expr = f"if(lt(t,{hold_start}),(t-{start_time})/{fade_in},if(lt(t,{hold_end}),1,({end_time}-t)/{fade_out}))"
        
        # Optional zoom/pop effect: scale text size based on time
        # Peak at middle of word duration
        mid_time = (start_time + end_time) / 2
        duration = end_time - start_time
        zoom_expr = f"if(lt(t,{mid_time}),1+0.1*(t-{start_time})/{duration},1+0.1*(1-({end_time}-t)/{duration}))"
        
        # Position: center horizontally, lower third vertically
        center_x = (video_width // 2)
        center_y = int(video_height * 0.65)
        
        # Construct drawtext filter
        # Using expansion: enable, fontsize, fontcolor, text, x, y, line_spacing
        drawtext = (
            f"drawtext="
            f"fontfile='/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf':"
            f"text='{word}':"
            f"fontsize={font_size}:"
            f"fontcolor={text_color}:"
            f"borderw=3:"
            f"bordercolor={outline_color}:"
            f"x=(w-text_w)/2:"  # Center horizontally
            f"y=h*0.65:"  # Lower third
            f"alpha={alpha_expr}:"
            f"enable='{enable_expr}'"
        )
        
        filters.append(drawtext)
    
    # Combine all filters with scale at the beginning
    combined = "scale=360:640"
    for filter_str in filters:
        combined += f",{filter_str}"
    
    return combined


def generate_word_by_word_captions(
    video_path: str,
    audio_path: str,
    words: List[Dict],
    output_path: str
) -> str:
    """Generate video with word-by-word animated captions.
    
    Args:
        video_path: Path to input video
        audio_path: Path to input audio
        words: List of word dicts from Deepgram with timing
        output_path: Path to save output video
        
    Returns:
        Path to output video
    """
    
    if not os.path.exists(video_path):
        raise RuntimeError(f"Video file not found: {video_path}")
    if not os.path.exists(audio_path):
        raise RuntimeError(f"Audio file not found: {audio_path}")
    
    print(f"[CAPTION ANIMATOR] Video: {video_path}", file=sys.stderr)
    print(f"[CAPTION ANIMATOR] Audio: {audio_path}", file=sys.stderr)
    print(f"[CAPTION ANIMATOR] Words to animate: {len(words)}", file=sys.stderr)
    
    if not words:
        print(f"[CAPTION ANIMATOR] No words provided, copying video as-is", file=sys.stderr)
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", audio_path,
            "-c:v", "libx264", "-preset", "fast",
            "-c:a", "aac",
            "-shortest",
            output_path
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        return output_path
    
    # Generate filter string
    filter_str = _generate_drawtext_filter(words)
    
    print(f"[CAPTION ANIMATOR] Generating FFmpeg command...", file=sys.stderr)
    
    # FFmpeg command with drawtext filter for word-by-word animation
    cmd = [
        "ffmpeg", "-y",
        "-stream_loop", "-1",  # Loop video if shorter than audio
        "-i", video_path,
        "-i", audio_path,
        "-map", "0:v",
        "-map", "1:a",
        "-c:v", "libx264",
        "-preset", "ultrafast",  # Fast for GPU
        "-crf", "28",  # Balance quality and speed
        "-vf", filter_str,
        "-c:a", "aac",
        "-shortest",  # Stop at shortest input
        output_path
    ]
    
    print(f"[CAPTION ANIMATOR] Running FFmpeg...", file=sys.stderr)
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        error_msg = result.stderr[-500:] if result.stderr else "Unknown error"
        print(f"[CAPTION ANIMATOR ERROR]\n{error_msg}", file=sys.stderr)
        raise RuntimeError(f"FFmpeg failed: {error_msg}")
    
    print(f"[CAPTION ANIMATOR] Success: {output_path}", file=sys.stderr)
    return output_path
