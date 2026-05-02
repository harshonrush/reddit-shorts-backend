from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from datetime import datetime, timedelta
import os
import tempfile
import requests
from db import supabase


def refresh_token_if_needed(creds: Credentials, user_id: str) -> Credentials:
    """Refresh access token if expired or about to expire."""
    if not creds:
        return creds

    # Refresh if expired or expiring in < 5 minutes
    if creds.expired or (creds.expiry and datetime.utcnow() >= (creds.expiry - timedelta(minutes=5))):
        if not creds.refresh_token:
            print("[TOKEN] No refresh token available")
            return creds

        print("[TOKEN] Refreshing access token...")
        creds.refresh(Request())

        # Update DB with new token
        supabase.table("user_tokens").update({
            "access_token": creds.token,
            "expiry": creds.expiry.isoformat() if creds.expiry else None
        }).eq("user_id", user_id).execute()

        print("[TOKEN] Token refreshed and saved to DB")

    return creds


def load_credentials_from_supabase(user_id: str) -> Credentials:
    """Load YouTube credentials from Supabase user_tokens table."""
    res = supabase.table("user_tokens").select("*").eq("user_id", user_id).execute()
    
    if not res.data:
        raise FileNotFoundError(f"Token not found for user {user_id}. Visit /auth/connect first to authenticate.")
    
    token_data = res.data[0]
    
    # Parse expiry from ISO string
    expiry_str = token_data.get("expiry")
    expiry = datetime.fromisoformat(expiry_str) if expiry_str else None
    
    creds = Credentials(
        token=token_data["access_token"],
        refresh_token=token_data["refresh_token"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.getenv("GOOGLE_CLIENT_ID", ""),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET", ""),
        scopes=["https://www.googleapis.com/auth/youtube.upload"],
        expiry=expiry
    )
    
    # Refresh if expiring in < 5 minutes
    if expiry and (expiry - timedelta(minutes=5)) < datetime.utcnow():
        creds.refresh(Request())
        
        # Update Supabase with new tokens
        supabase.table("user_tokens").upsert({
            "user_id": user_id,
            "access_token": creds.token,
            "refresh_token": creds.refresh_token,
            "expiry": creds.expiry.isoformat() if creds.expiry else None
        }, on_conflict="user_id").execute()
    
    return creds


def upload_video(video_url: str = None, file_path: str = None, title: str = "", description: str = "", tags: list = None, user_id: str = "default", token_data: dict = None) -> dict:
    """Upload video to YouTube using OAuth token.
    
    Args:
        video_url: URL to video file (downloaded before upload)
        file_path: Path to local video file (alternative to URL)
        title: Video title
        description: Video description
        tags: List of tags (optional)
        user_id: User identifier for token lookup
        token_data: Pre-fetched token data (optional, saves DB query)
        
    Returns:
        YouTube API response with video ID
    """
    # Download video from URL if provided
    downloaded = False
    if video_url and not file_path:
        print(f"[UPLOADER] Downloading video from {video_url}...")
        temp_file = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        response = requests.get(video_url, stream=True, timeout=120)
        response.raise_for_status()
        for chunk in response.iter_content(chunk_size=8192):
            temp_file.write(chunk)
        temp_file.close()
        file_path = temp_file.name
        downloaded = True
        print(f"[UPLOADER] Video downloaded to {file_path}")
    
    if not file_path:
        raise ValueError("Either video_url or file_path must be provided")
    
    print("[UPLOADER] STEP 1: Loading credentials...")
    if token_data:
        # Use pre-fetched token (saves DB query)
        # Convert expiry string to datetime if needed
        expiry = token_data.get("expiry")
        if isinstance(expiry, str):
            expiry = datetime.fromisoformat(expiry)

        creds = Credentials(
            token=token_data["access_token"],
            refresh_token=token_data.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=os.getenv("GOOGLE_CLIENT_ID", ""),
            client_secret=os.getenv("GOOGLE_CLIENT_SECRET", ""),
            scopes=["https://www.googleapis.com/auth/youtube.upload"],
            expiry=expiry
        )
        # Refresh if needed
        creds = refresh_token_if_needed(creds, user_id)
    else:
        # Fallback: fetch from DB
        creds = load_credentials_from_supabase(user_id)

    print("[UPLOADER] STEP 2: Building YouTube API client...")
    youtube = build("youtube", "v3", credentials=creds)

    if tags is None:
        tags = ["shorts", "reddit", "story"]

    print("[UPLOADER] STEP 3: Preparing video upload request...")
    request = youtube.videos().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags,
                "categoryId": "22"  # People & Blogs
            },
            "status": {
                "privacyStatus": "public"
            }
        },
        media_body=MediaFileUpload(file_path, chunksize=-1, resumable=True)
    )

    print("[UPLOADER] STEP 4: Sending to YouTube API...")
    try:
        response = request.execute()
        print(f"[UPLOADER] STEP 5: Upload response received: {response}")
        print(f"✅ Uploaded to YouTube: https://youtube.com/watch?v={response['id']}")
        return response
    finally:
        # Cleanup temp file if we downloaded it
        if downloaded and file_path and os.path.exists(file_path):
            try:
                os.unlink(file_path)
                print(f"[UPLOADER] Cleaned up temp file: {file_path}")
            except Exception as e:
                print(f"[UPLOADER] Failed to cleanup temp file: {e}")
