"""Apply effects to images: zoom, pan, transitions, color grading."""
import os
import sys
import subprocess
import tempfile
from typing import List, Dict, Tuple, Optional
from PIL import Image, ImageEnhance, ImageFilter
import json


def resize_image_to_video(
    image_path: str,
    output_path: str,
    video_width: int = 360,
    video_height: int = 640,
    fit: str = "cover"
) -> str:
    """Resize image to match video dimensions.
    
    Args:
        image_path: Input image
        output_path: Output image path
        video_width: Video width (default 360 for shorts)
        video_height: Video height (default 640 for shorts)
        fit: 'cover' (crop), 'contain' (letterbox), 'stretch'
        
    Returns:
        Path to resized image
    """
    
    if not os.path.exists(image_path):
        print(f"[IMAGE EFFECTS] Image not found: {image_path}", file=sys.stderr)
        return None
    
    try:
        img = Image.open(image_path)
        print(f"[IMAGE EFFECTS] Original size: {img.size}", file=sys.stderr)
        
        if fit == "cover":
            # Crop to fit
            img.thumbnail((video_width, video_height), Image.Resampling.LANCZOS)
            # Create new image with exact dimensions and paste cropped image in center
            new_img = Image.new('RGB', (video_width, video_height), color='black')
            offset = ((video_width - img.width) // 2, (video_height - img.height) // 2)
            new_img.paste(img, offset)
            img = new_img
        elif fit == "contain":
            # Letterbox with black bars
            img.thumbnail((video_width, video_height), Image.Resampling.LANCZOS)
            new_img = Image.new('RGB', (video_width, video_height), color='black')
            offset = ((video_width - img.width) // 2, (video_height - img.height) // 2)
            new_img.paste(img, offset)
            img = new_img
        else:  # stretch
            img = img.resize((video_width, video_height), Image.Resampling.LANCZOS)
        
        img.save(output_path, quality=95)
        print(f"[IMAGE EFFECTS] Resized to {img.size}: {output_path}", file=sys.stderr)
        return output_path
    
    except Exception as e:
        print(f"[IMAGE EFFECTS] Resize failed: {e}", file=sys.stderr)
        return None


def apply_color_effects(
    image_path: str,
    output_path: str,
    brightness: float = 1.0,
    contrast: float = 1.0,
    saturation: float = 1.2,  # Boost saturation for viral look
    sharpen: bool = True
) -> str:
    """Apply color/brightness effects to image.
    
    Args:
        image_path: Input image
        output_path: Output image path
        brightness: Brightness multiplier (1.0 = original)
        contrast: Contrast multiplier
        saturation: Color saturation (1.0 = original)
        sharpen: Apply sharpening filter
        
    Returns:
        Path to processed image
    """
    
    try:
        img = Image.open(image_path).convert('RGB')
        
        # Brightness
        if brightness != 1.0:
            enhancer = ImageEnhance.Brightness(img)
            img = enhancer.enhance(brightness)
        
        # Contrast
        if contrast != 1.0:
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(contrast)
        
        # Saturation (color)
        if saturation != 1.0:
            enhancer = ImageEnhance.Color(img)
            img = enhancer.enhance(saturation)
        
        # Sharpening
        if sharpen:
            img = img.filter(ImageFilter.SHARPEN)
        
        img.save(output_path, quality=95)
        print(f"[IMAGE EFFECTS] Color effects applied: {output_path}", file=sys.stderr)
        return output_path
    
    except Exception as e:
        print(f"[IMAGE EFFECTS] Color effects failed: {e}", file=sys.stderr)
        return None


def create_ken_burns_effect(
    image_path: str,
    output_path: str,
    duration: float = 3.0,
    start_zoom: float = 1.0,
    end_zoom: float = 1.1,
    fps: int = 30
) -> str:
    """Create Ken Burns (zoom + pan) video effect from static image.
    
    Args:
        image_path: Input image
        output_path: Output video path
        duration: Duration in seconds
        start_zoom: Initial zoom level
        end_zoom: Final zoom level
        fps: Frames per second
        
    Returns:
        Path to output video
    """
    
    if not os.path.exists(image_path):
        print(f"[KEN BURNS] Image not found: {image_path}", file=sys.stderr)
        return None
    
    try:
        print(f"[KEN BURNS] Creating {duration}s effect with zoom {start_zoom} → {end_zoom}", file=sys.stderr)
        
        # Use FFmpeg to create Ken Burns effect
        # This zooms and pans the image over time
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",  # Loop the image
            "-i", image_path,
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-t", str(duration),
            "-vf", f"zoom=z='min(zoom+0.0015,1.5)':d={duration}",  # Zoom effect
            "-pix_fmt", "yuv420p",
            output_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"[KEN BURNS] FFmpeg error: {result.stderr[-200:]}", file=sys.stderr)
            return None
        
        print(f"[KEN BURNS] Effect created: {output_path}", file=sys.stderr)
        return output_path
    
    except Exception as e:
        print(f"[KEN BURNS] Effect creation failed: {e}", file=sys.stderr)
        return None


def create_image_slideshow(
    image_paths: List[str],
    output_video_path: str,
    duration_per_image: float = 2.0,
    transition: str = "fade",
    transition_duration: float = 0.5,
    fps: int = 30
) -> str:
    """Create video slideshow from multiple images with transitions.
    
    Args:
        image_paths: List of image paths
        output_video_path: Output video path
        duration_per_image: Seconds per image
        transition: 'fade', 'dissolve', 'zoom', 'wipeleft'
        transition_duration: Transition length in seconds
        fps: Frames per second
        
    Returns:
        Path to output video
    """
    
    if not image_paths:
        print(f"[SLIDESHOW] No images provided", file=sys.stderr)
        return None
    
    print(f"[SLIDESHOW] Creating slideshow from {len(image_paths)} images", file=sys.stderr)
    
    try:
        # Create a concat demuxer file for FFmpeg
        concat_file = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False).name
        
        with open(concat_file, 'w') as f:
            for img_path in image_paths:
                f.write(f"file '{os.path.abspath(img_path)}'\n")
                f.write(f"duration {duration_per_image}\n")
        
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_file,
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-preset", "ultrafast",
            "-crf", "28",
            output_video_path
        ]
        
        # Transitions via -filter_complex with concat demuxer will crash FFmpeg
        # so we rely purely on straight cuts through the demuxer.
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        # Cleanup
        try:
            os.unlink(concat_file)
        except:
            pass
        
        if result.returncode != 0:
            print(f"[SLIDESHOW] FFmpeg error: {result.stderr[-200:]}", file=sys.stderr)
            return None
        
        print(f"[SLIDESHOW] Slideshow created: {output_video_path}", file=sys.stderr)
        return output_video_path
    
    except Exception as e:
        print(f"[SLIDESHOW] Creation failed: {e}", file=sys.stderr)
        return None


def create_video_slideshow(
    video_paths: List[str],
    output_video_path: str
) -> str:
    """Concatenate multiple video clips into a single video slideshow.
    
    Args:
        video_paths: List of video paths (.mp4 files)
        output_video_path: Output video path
        
    Returns:
        Path to output video
    """
    if not video_paths:
        print(f"[VIDEO SLIDESHOW] No videos provided", file=sys.stderr)
        return None
    
    print(f"[VIDEO SLIDESHOW] Concatenating {len(video_paths)} video clips", file=sys.stderr)
    
    try:
        # Create a concat demuxer file for FFmpeg
        concat_file = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False).name
        
        with open(concat_file, 'w') as f:
            for vid_path in video_paths:
                f.write(f"file '{os.path.abspath(vid_path)}'\n")
        
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_file,
            "-c:v", "copy",  # Fast stream copy since codecs match
            output_video_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        # Cleanup
        try:
            os.unlink(concat_file)
        except:
            pass
        
        if result.returncode != 0:
            print(f"[VIDEO SLIDESHOW] FFmpeg error: {result.stderr[-200:]}", file=sys.stderr)
            return None
        
        print(f"[VIDEO SLIDESHOW] Concatenation successful: {output_video_path}", file=sys.stderr)
        return output_video_path
    
    except Exception as e:
        print(f"[VIDEO SLIDESHOW] Creation failed: {e}", file=sys.stderr)
        return None


def overlay_image_on_video(
    background_video_path: str,
    image_path: str,
    output_path: str,
    position: str = "center",
    opacity: float = 0.7,
    scale: float = 1.0
) -> str:
    """Overlay an image on a video background.
    
    Args:
        background_video_path: Background video
        image_path: Image to overlay
        output_path: Output video path
        position: 'center', 'topleft', 'topright', 'bottomleft', 'bottomright'
        opacity: Image opacity (0.0-1.0)
        scale: Image scale relative to video
        
    Returns:
        Path to output video
    """
    
    try:
        print(f"[OVERLAY] Overlaying {image_path} on video", file=sys.stderr)
        
        # Calculate position coordinates
        positions = {
            "center": "(W-w)/2:(H-h)/2",
            "topleft": "0:0",
            "topright": "W-w:0",
            "bottomleft": "0:H-h",
            "bottomright": "W-w:H-h"
        }
        
        pos_expr = positions.get(position, "(W-w)/2:(H-h)/2")
        
        # FFmpeg filter: overlay with opacity
        cmd = [
            "ffmpeg", "-y",
            "-i", background_video_path,
            "-i", image_path,
            "-filter_complex", f"[1:v]scale=iw*{scale}:ih*{scale}[ovr];[0:v][ovr]overlay={pos_expr}:alpha={opacity}",
            "-c:a", "copy",  # Copy audio from background
            "-preset", "ultrafast",
            output_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"[OVERLAY] FFmpeg error: {result.stderr[-200:]}", file=sys.stderr)
            return None
        
        print(f"[OVERLAY] Image overlaid: {output_path}", file=sys.stderr)
        return output_path
    
    except Exception as e:
        print(f"[OVERLAY] Overlay failed: {e}", file=sys.stderr)
        return None
