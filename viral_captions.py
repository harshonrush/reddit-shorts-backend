"""FFmpeg-based viral captions using SRT subtitles - clean and stable."""
import os
import subprocess
import sys
import tempfile
from typing import List, Dict


def _format_srt_time(seconds: float) -> str:
    """Convert seconds to SRT time format HH:MM:SS,mmm."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _generate_srt(words: List[Dict], output_path: str):
    """Generate SRT subtitle file from word timestamps - VIRAL STYLE."""
    # VIRAL: Short lines (max 3 words), ALL CAPS
    max_per_line = 3
    lines = []
    current_line = []
    
    for word in words:
        # Clean word: remove extra punctuation for viral look
        clean_word = word["word"].strip(".,!?;:")
        if clean_word:
            current_line.append({
                "word": clean_word,
                "start": word["start"],
                "end": word["end"]
            })
        # Break on sentence end or max words
        if len(current_line) >= max_per_line or word["word"].endswith((".", "!", "?")):
            lines.append(current_line)
            current_line = []
    
    if current_line:
        lines.append(current_line)
    
    # Write SRT file - ALL CAPS for viral impact
    with open(output_path, "w", encoding="utf-8") as f:
        for idx, line_words in enumerate(lines, 1):
            start_time = line_words[0]["start"]
            end_time = line_words[-1]["end"]
            # VIRAL: ALL CAPS
            text = " ".join(w["word"] for w in line_words).upper()
            
            f.write(f"{idx}\n")
            f.write(f"{_format_srt_time(start_time)} --> {_format_srt_time(end_time)}\n")
            f.write(f"{text}\n\n")


def generate_viral_captions_ffmpeg(
    video_path: str,
    audio_path: str,
    words: List[Dict],
    output_path: str,
    loop_video: bool = True,
    bg_music_path: str = None
):
    """Generate viral-style video with SRT subtitles.
    
    Features:
    - Clean SRT-based subtitles (no escaping hell)
    - Big bold styling via FFmpeg subtitle filter
    - Center-bottom positioning
    - Optional background music mixing with auto ducking
    """
    
    # Validate inputs exist
    if not os.path.exists(video_path):
        raise RuntimeError(f"Video file not found: {video_path}")
    if not os.path.exists(audio_path):
        raise RuntimeError(f"Audio file not found: {audio_path}")
    
    print(f"[FFMPEG] Video: {video_path} ({os.path.getsize(video_path)} bytes)", file=sys.stderr)
    print(f"[FFMPEG] Audio: {audio_path} ({os.path.getsize(audio_path)} bytes)", file=sys.stderr)
    if bg_music_path:
        print(f"[FFMPEG] BG Music: {bg_music_path}", file=sys.stderr)
    print(f"[FFMPEG] Words: {len(words)}", file=sys.stderr)
    
    if not words:
        # No captions, just mix and copy
        print(f"[FFMPEG] No words provided, mixing audio as-is", file=sys.stderr)
        cmd = ["ffmpeg", "-y"]
        if loop_video:
            cmd.extend(["-stream_loop", "-1"])
        cmd.extend(["-i", video_path, "-i", audio_path])
        
        if bg_music_path and os.path.exists(bg_music_path):
            cmd.extend(["-stream_loop", "-1", "-i", bg_music_path])
            
        cmd.extend([
            "-c:v", "libx264", "-preset", "fast",
        ])
        
        if bg_music_path and os.path.exists(bg_music_path):
            cmd.extend([
                "-filter_complex", "[2:a]volume=0.15[bg];[1:a][bg]amix=inputs=2:duration=first:dropout_transition=2[out_audio]",
                "-map", "0:v",
                "-map", "[out_audio]"
            ])
        else:
            cmd.extend([
                "-map", "0:v",
                "-map", "1:a"
            ])
            
        cmd.extend([
            "-c:a", "aac",
            "-shortest",
            output_path
        ])
        subprocess.run(cmd, check=True)
        return output_path
    
    # Generate SRT file
    srt_path = tempfile.NamedTemporaryFile(suffix=".srt", delete=False).name
    _generate_srt(words, srt_path)
    
    # Escape SRT path for FFmpeg (spaces, special chars)
    srt_path_escaped = srt_path.replace("\\", "\\\\").replace(":", "\\:")
    
    # FFmpeg with subtitles filter (-vf is cleaner than -filter_complex)
    # Font: DejaVu Sans (available on Linux), big viral style
    cmd = ["ffmpeg", "-y"]
    if loop_video:
        cmd.extend(["-stream_loop", "-1"])  # Loop video infinitely to match audio
        
    cmd.extend([
        "-i", video_path,
        "-i", audio_path,
    ])
    
    if bg_music_path and os.path.exists(bg_music_path):
        cmd.extend(["-stream_loop", "-1", "-i", bg_music_path])
        
    cmd.extend([
        "-c:v", "libx264", "-preset", "fast", "-crf", "30",
        "-vf", f"subtitles='{srt_path_escaped}':force_style='FontSize=24,FontName=DejaVu Sans,Bold=1,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=5,Alignment=2,MarginV=100',scale=360:640",
    ])
    
    if bg_music_path and os.path.exists(bg_music_path):
        cmd.extend([
            "-filter_complex", "[2:a]volume=0.15[bg];[1:a][bg]amix=inputs=2:duration=first:dropout_transition=2[out_audio]",
            "-map", "0:v",
            "-map", "[out_audio]"
        ])
    else:
        cmd.extend([
            "-map", "0:v",
            "-map", "1:a"
        ])
        
    cmd.extend([
        "-c:a", "aac",
        "-shortest",  # Stop when shortest input (audio) ends
        output_path
    ])
    
    print(f"[FFMPEG] Running with SRT subtitles...", file=sys.stderr)
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    # Cleanup temp file
    try:
        os.unlink(srt_path)
    except:
        pass
    
    if result.returncode != 0:
        print(f"[FFMPEG ERROR FULL]\n{result.stderr}", file=sys.stderr)
        raise RuntimeError(f"FFmpeg failed: {result.stderr}")
    
    print(f"[FFMPEG] Viral captions added: {output_path}", file=sys.stderr)
    return output_path



# Alias for compatibility
generate_animated_captions = generate_viral_captions_ffmpeg
