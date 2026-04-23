from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
import os
from db import supabase


def load_credentials_from_supabase(user_id: str) -> Credentials:
    """Load YouTube credentials from Supabase user_tokens table."""
    res = supabase.table("user_tokens").select("*").eq("user_id", user_id).execute()
    
    if not res.data:
        raise FileNotFoundError(f"Token not found for user {user_id}. Visit /auth/connect first to authenticate.")
    
    token_data = res.data[0]
    
    return Credentials(
        token=token_data["access_token"],
        refresh_token=token_data["refresh_token"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.getenv("GOOGLE_CLIENT_ID", ""),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET", ""),
        scopes=["https://www.googleapis.com/auth/youtube.upload"],
        expiry=token_data.get("expiry")
    )


def upload_video(file_path: str, title: str, description: str = "", tags: list = None, user_id: str = "default") -> dict:
    """Upload video to YouTube using OAuth token from Supabase.
    
    Args:
        file_path: Path to video file
        title: Video title
        description: Video description
        tags: List of tags (optional)
        user_id: User identifier for token lookup
        
    Returns:
        YouTube API response with video ID
    """
    creds = load_credentials_from_supabase(user_id)
    youtube = build("youtube", "v3", credentials=creds)
    
    if tags is None:
        tags = ["shorts", "reddit", "story"]
    
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
        media_body=MediaFileUpload(file_path, resumable=True)
    )
    
    response = request.execute()
    print(f"✅ Uploaded to YouTube: https://youtube.com/watch?v={response['id']}")
    return response
