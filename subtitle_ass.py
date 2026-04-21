from pydub import AudioSegment

def generate_ass(script, audio_path, path):
    """Generate ASS subtitles with timing based on audio duration.
    
    Args:
        script: The video script text
        audio_path: Path to audio file (for duration calculation)
        path: Path to save .ass file
        
    Returns:
        Path to generated ASS file
    """
    # Get audio duration
    audio = AudioSegment.from_file(audio_path)
    total_duration = len(audio) / 1000  # seconds

    words = script.split()
    words_per_line = 3

    # Break into short punchy lines
    lines = [
        " ".join(words[i:i+words_per_line])
        for i in range(0, len(words), words_per_line)
    ]

    time_per_line = total_duration / len(lines) if lines else 2.0

    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Alignment
Style: Default,Arial,90,&H00FFFFFF,&H00000000,&H64000000,1,2

[Events]
Format: Layer, Start, End, Style, Text
"""

    with open(path, "w", encoding="utf-8") as f:
        f.write(header)

        for i, line in enumerate(lines):
            start = i * time_per_line
            end = start + time_per_line

            start_time = f"0:00:{int(start):02}.{int((start%1)*100):02}"
            end_time = f"0:00:{int(end):02}.{int((end%1)*100):02}"

            f.write(f"Dialogue: 0,{start_time},{end_time},Default,{line}\n")

    return path