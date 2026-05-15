import subprocess
import tempfile
import os

with open("test1.jpg", "w") as f:
    f.write("dummy") # Not a real image, but enough to see the command error
with open("test2.jpg", "w") as f:
    f.write("dummy")

concat_file = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False).name
with open(concat_file, 'w') as f:
    f.write(f"file '{os.path.abspath('test1.jpg')}'\n")
    f.write(f"duration 2.0\n")
    f.write(f"file '{os.path.abspath('test2.jpg')}'\n")
    f.write(f"duration 2.0\n")

cmd = [
    "ffmpeg", "-y",
    "-f", "concat",
    "-safe", "0",
    "-i", concat_file,
    "-c:v", "libx264",
    "-preset", "ultrafast",
    "-crf", "28",
    "-filter_complex", "xfade=transition=fade:duration=0.5",
    "output.mp4"
]

result = subprocess.run(cmd, capture_output=True, text=True)
print("Return code:", result.returncode)
print("Stderr:", result.stderr[-200:])
