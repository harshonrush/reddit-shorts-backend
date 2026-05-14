import runpod
import sys
import tempfile
import os
import shutil

from script_engine import generate_script
from tts import generate_audio
from video_fetcher import fetch_video
from subtitle import get_word_timestamps  # Deepgram transcription only
from viral_captions import generate_animated_captions  # FFmpeg viral captions
from caption_animator import generate_word_by_word_captions  # Word-by-word animation
from image_generator import generate_image_prompts  # Gemini image prompts
from pexels_integration import fetch_images_for_scenes  # Pexels API
from image_effects import (
    resize_image_to_video,
    apply_color_effects,
    create_ken_burns_effect,
    create_image_slideshow,
    overlay_image_on_video
)
from storage import upload_video_bytes  # Direct upload to Supabase
from config import VOICE_MAP, LANGUAGE_PROMPTS


def handler(job):
    """Generate video on RunPod GPU — Railway handles upload.
    
    Supports:
    - Word-by-word animated captions (caption_style: 'word-by-word')
    - Viral line-by-line captions (caption_style: 'viral')
    - Gemini-generated images + Pexels (enable_images: true)
    - Ken Burns effects on images
    """
    audio_path = None
    video_path = None
    output_path = None
    temp_dir = None

    try:
        print("[RUNPOD] Job received", file=sys.stderr)

        # Get settings from input
        voice = job["input"].get("voice", "male_deep")
        language = job["input"].get("language", "english")
        video_style = job["input"].get("video_style", "gameplay")
        niche = job["input"].get("niche", "general")
        
        # NEW: Caption style selector
        caption_style = job["input"].get("caption_style", "viral")  # 'viral' or 'word-by-word'
        
        # NEW: Image features
        enable_images = job["input"].get("enable_images", False)
        use_user_video = job["input"].get("use_user_video", False)  # Use provided video instead of fetching
        user_video_path = job["input"].get("user_video_path", None)
        
        # Map voice to ElevenLabs ID
        voice_id = VOICE_MAP.get(voice, VOICE_MAP["male_deep"])
        
        # Use provided script directly, or generate from topic if not provided
        script = job["input"].get("script")
        if not script:
            topic = job["input"].get("topic", "success mindset")
            # Add language instruction to topic
            lang_prompt = LANGUAGE_PROMPTS.get(language, LANGUAGE_PROMPTS["english"])
            full_topic = f"{topic}. {lang_prompt}."
            script = generate_script(full_topic)
            print(f"[RUNPOD] Generated script from topic: {topic} (lang: {language})", file=sys.stderr)
        else:
            print(f"[RUNPOD] Using provided script: {script[:50]}...", file=sys.stderr)

        # 3. Temp files & directory (secure)
        temp_dir = tempfile.mkdtemp(prefix="runpod_")
        audio_path = os.path.join(temp_dir, "audio.mp3")
        video_path = os.path.join(temp_dir, "base_video.mp4")
        output_path = os.path.join(temp_dir, "output.mp4")
        images_dir = os.path.join(temp_dir, "images")

        print(f"[RUNPOD] Temp directory: {temp_dir}", file=sys.stderr)

        # 4. Step 1: Generate audio
        print(f"[RUNPOD] Step 1: Generating audio with voice {voice_id}...", file=sys.stderr)
        try:
            generate_audio(script, audio_path, voice_id=voice_id)
        except Exception as e:
            print(f"[RUNPOD ERROR] TTS generation failed: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            raise Exception(f"TTS failed: {e}")
        
        # Verify audio file exists and has content
        if not os.path.exists(audio_path):
            raise Exception(f"Audio file not created at {audio_path}")
        
        audio_size = os.path.getsize(audio_path)
        print(f"[RUNPOD] Audio generated: {audio_size} bytes", file=sys.stderr)
        if audio_size < 1000:
            raise Exception(f"Audio file too small ({audio_size} bytes) - TTS failed")
        
        # 5. Step 2: Get video (use user-provided or fetch)
        print(f"[RUNPOD] Step 2: Getting video...", file=sys.stderr)
        if use_user_video and user_video_path and os.path.exists(user_video_path):
            print(f"[RUNPOD] Using user-provided video: {user_video_path}", file=sys.stderr)
            shutil.copy(user_video_path, video_path)
        else:
            print(f"[RUNPOD] Fetching video with style {video_style}...", file=sys.stderr)
            fetch_video(video_path, style=video_style)
        
        video_size = os.path.getsize(video_path)
        print(f"[RUNPOD] Video ready: {video_size} bytes", file=sys.stderr)
        if video_size < 10000:
            raise Exception(f"Video file too small ({video_size} bytes) - fetch failed")
        
        # 6. Step 3: NEW - Generate images if enabled
        images_applied = False
        if enable_images:
            print(f"[RUNPOD] Step 3a: Generating scene descriptions for images...", file=sys.stderr)
            try:
                scene_prompts = generate_image_prompts(script, niche=niche)
                print(f"[RUNPOD] Generated {len(scene_prompts)} image prompts", file=sys.stderr)
                
                # Fetch images from Pexels
                print(f"[RUNPOD] Step 3b: Fetching images from Pexels...", file=sys.stderr)
                fetched_images = fetch_images_for_scenes(scene_prompts, images_dir, fallback_niche=niche)
                successful_images = [img for img in fetched_images if img["status"] == "success"]
                
                if successful_images and len(successful_images) > 0:
                    print(f"[RUNPOD] Successfully fetched {len(successful_images)}/{len(fetched_images)} images", file=sys.stderr)
                    
                    # Step 3c: Apply effects to images
                    print(f"[RUNPOD] Step 3c: Applying color effects to {len(successful_images)} images...", file=sys.stderr)
                    processed_images = []
                    for img_data in successful_images:
                        img_path = img_data["image_path"]
                        effects_path = img_path.replace(".jpg", "_effects.jpg")
                        
                        # Resize to video dimensions
                        if not resize_image_to_video(img_path, img_path, fit="cover"):
                            print(f"[RUNPOD] Warning: Failed to resize {img_path}", file=sys.stderr)
                            continue
                        
                        # Apply color effects (boost saturation for viral look)
                        if not apply_color_effects(img_path, effects_path, 
                                              brightness=1.05, 
                                              contrast=1.15, 
                                              saturation=1.3):
                            print(f"[RUNPOD] Warning: Failed to apply effects to {img_path}", file=sys.stderr)
                            continue
                        
                        processed_images.append(effects_path)
                    
                    if processed_images:
                        # Step 3d: Create slideshow from processed images
                        print(f"[RUNPOD] Step 3d: Creating slideshow from {len(processed_images)} images...", file=sys.stderr)
                        slideshow_path = os.path.join(temp_dir, "slideshow.mp4")
                        
                        # Calculate duration per image based on audio length
                        try:
                            from subtitle_ass import get_audio_duration
                            audio_duration = get_audio_duration(audio_path)
                            duration_per_image = audio_duration / len(processed_images)
                            print(f"[RUNPOD] Audio duration: {audio_duration}s, per image: {duration_per_image}s", file=sys.stderr)
                        except:
                            duration_per_image = 2.0  # Fallback
                        
                        slideshow_created = create_image_slideshow(
                            processed_images,
                            slideshow_path,
                            duration_per_image=duration_per_image,
                            transition="fade"
                        )
                        
                        if slideshow_created:
                            # Replace video_path with slideshow
                            video_path = slideshow_path
                            images_applied = True
                            print(f"[RUNPOD] Slideshow created successfully: {video_path}", file=sys.stderr)
                        else:
                            print(f"[RUNPOD] Failed to create slideshow, using original video", file=sys.stderr)
                    else:
                        print(f"[RUNPOD] No images after effects processing, using original video", file=sys.stderr)
                else:
                    print(f"[RUNPOD] No images fetched ({len(successful_images)}/{len(fetched_images)}), continuing with default video", file=sys.stderr)
            
            except Exception as e:
                print(f"[RUNPOD] Image generation failed: {e} - continuing with default video", file=sys.stderr)
                import traceback
                traceback.print_exc(file=sys.stderr)
        
        # 7. Step 4: Get word timestamps from Deepgram
        print(f"[RUNPOD] Step 4: Getting word timestamps...", file=sys.stderr)
        words = get_word_timestamps(audio_path)
        print(f"[RUNPOD] Got {len(words)} words for captions", file=sys.stderr)
        if not words:
            print(f"[RUNPOD WARNING] No words detected - captions will be empty", file=sys.stderr)
        
        # 8. Step 5: Generate captions (with style selector)
        print(f"[RUNPOD] Step 5: Generating {caption_style} captions...", file=sys.stderr)
        
        if caption_style == "word-by-word" and words:
            # NEW: Word-by-word animated captions
            print(f"[RUNPOD] Using word-by-word animated captions", file=sys.stderr)
            generate_word_by_word_captions(video_path, audio_path, words, output_path)
        else:
            # Default: Viral line-by-line captions
            print(f"[RUNPOD] Using viral line-by-line captions", file=sys.stderr)
            generate_animated_captions(video_path, audio_path, words, output_path)
        
        output_size = os.path.getsize(output_path)
        print(f"[RUNPOD] Captions applied: {output_size} bytes", file=sys.stderr)
        if output_size < 10000:
            raise Exception(f"Output video too small ({output_size} bytes) - caption generation failed")

        print("[RUNPOD] Video rendered successfully", file=sys.stderr)

        # Read video and upload directly to Supabase Storage
        with open(output_path, "rb") as f:
            video_bytes = f.read()
        
        user_id = job["input"].get("user_id", "anonymous")
        job_id = job["id"]
        video_url = upload_video_bytes(video_bytes, user_id, job_id)

        print(f"[RUNPOD] Video uploaded: {video_url}", file=sys.stderr)
        print(f"FINAL OUTPUT: {video_url}", file=sys.stderr)

        return {
            "output": {
                "video_url": video_url,
                "caption_style": caption_style,
                "images_applied": images_applied
            }
        }

    except Exception as e:
        print(f"[RUNPOD ERROR] {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}

    finally:
        # Cleanup temp directory
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
                print(f"[RUNPOD] Cleaned up temp directory", file=sys.stderr)
            except Exception as e:
                print(f"[RUNPOD] Warning: Failed to cleanup temp dir: {e}", file=sys.stderr)


runpod.serverless.start({"handler": handler})
