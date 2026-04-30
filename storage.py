"""Supabase Storage upload helper"""
from db import supabase


def upload_video_bytes(video_bytes: bytes, user_id: str, job_id: str) -> str:
    """Upload video bytes to Supabase Storage and return public URL."""
    file_path = f"{user_id}/{job_id}.mp4"

    res = supabase.storage.from_("videos").upload(
        file_path,
        video_bytes,
        {"content-type": "video/mp4"}
    )

    if hasattr(res, "error") and res.error:
        raise Exception(f"Upload failed: {res.error}")

    # Handle both old and new supabase client versions
    if isinstance(res, dict) and res.get("error"):
        raise Exception(f"Upload failed: {res['error']}")

    public_url = supabase.storage.from_("videos").get_public_url(file_path)

    return public_url
