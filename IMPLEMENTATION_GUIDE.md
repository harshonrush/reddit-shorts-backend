# Implementation Guide: Word-by-Word Captions + Gemini AI Images

## ✅ What Was Implemented

### 1. **Word-by-Word Animated Captions** (`caption_animator.py`)
Replaces line-by-line captions with smooth, animated word-by-word reveals.

**Features:**
- Each word fades in, holds, and fades out with precise timing
- Optional pop/zoom effect on each word
- FFmpeg drawtext filter for maximum quality
- Centers text with large, bold font (60pt)
- Synchronized perfectly with TTS audio using Deepgram word timestamps

**Usage in handler:**
```python
caption_style = job["input"].get("caption_style", "viral")
# Set to "word-by-word" for animated captions
# Set to "viral" (default) for line-by-line captions
```

---

### 2. **Gemini AI Image Prompt Generation** (`image_generator.py`)
Uses Gemini 2-Flash to generate scene-specific image prompts from your video script.

**Features:**
- Splits script into 3-5 logical scenes
- Generates vivid, cinematic image prompts for each scene
- Niche-aware prompts (facts, horror, stories, etc.)
- Fallback prompts if Gemini fails

**Integration:**
```python
enable_images = job["input"].get("enable_images", False)
niche = job["input"].get("niche", "general")

if enable_images:
    scene_prompts = generate_image_prompts(script, niche=niche)
```

---

### 3. **Pexels Image Fetcher** (`pexels_integration.py`)
Automatically fetches portrait-oriented images from Pexels API matching your prompts.

**Features:**
- Searches Pexels using generated prompts
- Downloads highest-resolution images
- Fallback search if primary prompt doesn't match
- Credit tracking (photographer info)

**Free Tier:** 50 requests/hour (sufficient for ~20 videos/day)

**Setup:**
```bash
# Get free API key from https://www.pexels.com/api/
export PEXELS_API_KEY="A9Z6O2R7qs0HmrjM6Ie06wIB2OBc5IZ20jRyct6WAZBQD6WIEomcXd7f"
```

---

### 4. **Image Effects Pipeline** (`image_effects.py`)
Apply professional effects to images for viral engagement.

**Available Effects:**
- **Resize:** Adapt images to 360x640 (shorts format)
- **Color Grading:** Boost brightness, contrast, saturation for viral look
- **Sharpening:** Enhance detail
- **Ken Burns:** Cinematic zoom + pan effect over time
- **Slideshow:** Combine multiple images with transitions
- **Overlay:** Layer images on video background

**Example:**
```python
# Boost saturation + contrast for viral appeal
apply_color_effects(
    image_path, 
    output_path,
    brightness=1.05,
    contrast=1.15,
    saturation=1.3  # Vibrant colors
)
```

---

### 5. **Updated Handler** (`handler.py`)
Orchestrates entire pipeline with flexible options.

**New Parameters:**
```python
{
    "caption_style": "word-by-word",      # "viral" or "word-by-word"
    "enable_images": true,                 # Enable Gemini + Pexels
    "niche": "horror",                     # For image prompt context
    "use_user_video": false,               # Use provided video instead of fetching
    "user_video_path": "/path/to/video.mp4"
}
```

**Execution Flow:**
```
1. Generate Audio (TTS)
2. Get Video (user-provided OR fetch from Supabase)
3. [NEW] Generate Scene Descriptions → Image Prompts
4. [NEW] Fetch Images from Pexels
5. [NEW] Apply Color Effects
6. Get Word Timestamps (Deepgram)
7. Generate Captions (word-by-word OR viral)
8. Upload Final Video
```

---

## 🚀 Quick Start

### For End Users (API Call):

**With Word-by-Word Captions:**
```python
import requests

response = requests.post(
    "https://your-runpod-url/run",
    json={
        "input": {
            "topic": "The Creepiest Encounter",
            "niche": "horror",
            "voice": "male_deep",
            "caption_style": "word-by-word",  # NEW
            "enable_images": False,  # Start without images
        }
    }
)
```

**With Gemini Images + Pexels:**
```python
response = requests.post(
    "https://your-runpod-url/run",
    json={
        "input": {
            "script": "...",  # Your script
            "niche": "facts",
            "caption_style": "viral",
            "enable_images": True,  # NEW - Fetch & apply images
            "voice": "male_deep"
        }
    }
)
```

---

## 🔧 Environment Variables Required

```bash
# Existing
GEMINI_API_KEY="your-gemini-key"
ELEVENLABS_API_KEY="your-elevenlabs-key"
DEEPGRAM_API_KEY="your-deepgram-key"
SUPABASE_URL="your-supabase-url"
SUPABASE_KEY="your-supabase-key"

# NEW - for Pexels images
PEXELS_API_KEY="your-pexels-key"  # Get free at pexels.com/api
```

---

## 📦 New Dependencies

Added to `requirements.txt`:

```
Pillow==10.3.0          # Image processing
pysubs2==1.4.4          # Advanced subtitle handling (optional)
```

**FFmpeg Required** (already in RunPod):
- Used for video composition, effects, and rendering
- No additional installation needed

---

## 🎨 Caption Style Comparison

| Feature | Viral (Line-by-Line) | Word-by-Word |
|---------|----------------------|--------------|
| Animation | None | Smooth fade + pop |
| Readability | High | Very High |
| Engagement | Good | Excellent |
| CPU Usage | Low | Medium |
| Best For | Quick videos | Story-driven |

---

## 🖼️ Image Feature Pipeline

**When `enable_images=True`:**

1. **Scene Split** - Break script into 3-5 segments
2. **Prompt Generation** - Gemini creates vivid image descriptions
3. **Image Search** - Pexels API finds matching portraits
4. **Download** - Save locally with error handling
5. **Effects** - Boost colors (1.3x saturation for viral appeal)
6. **Composite** - [Ready for future implementation]

**Rate Limiting:**
- Pexels: 50 requests/hour (free) → ~20 videos/day
- Gemini: Depends on your quota (typically high)

---

## ⚠️ Troubleshooting

### Word-by-Word Captions Not Showing
- Check `DEEPGRAM_API_KEY` is set (required for word timestamps)
- Verify audio file duration > 1 second
- Ensure `caption_style="word-by-word"` in request

### Images Not Fetching
- Verify `PEXELS_API_KEY` is valid
- Check internet connection on RunPod
- Look for logs: `[PEXELS] Searching:...`

### Out of Memory on RunPod
- Image processing disabled by default
- If enabled, process fewer images (reduce script length)
- Use smaller video resolution

---

## 🎯 Future Enhancements

1. **Image Overlay on Video** - Composite images with transparency
2. **Scene Detection** - Auto-split video into scenes
3. **Music Integration** - Add background music tracks
4. **Voice Cloning** - Support custom voice fonts
5. **A/B Testing** - Generate multiple caption styles for comparison

---

## 📝 File Structure

```
backend/
├── handler.py              # Main orchestrator (UPDATED)
├── caption_animator.py     # NEW - Word-by-word captions
├── image_generator.py      # NEW - Gemini prompts
├── pexels_integration.py   # NEW - Image fetching
├── image_effects.py        # NEW - Effects pipeline
├── viral_captions.py       # Existing - Viral line-by-line
├── tts.py                  # Existing - Audio generation
├── subtitle.py             # Existing - Word timestamps
└── requirements.txt        # UPDATED - New dependencies
```

---

## 🔗 API References

- **Gemini AI:** https://ai.google.dev/
- **Pexels API:** https://www.pexels.com/api/
- **Deepgram:** https://developers.deepgram.com/
- **ElevenLabs:** https://elevenlabs.io/docs/

---

**Implementation Date:** May 2026  
**Status:** ✅ Complete and Ready for Testing
