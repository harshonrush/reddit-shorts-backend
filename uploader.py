from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
import os

TOKENS_DIR = "tokens"


def upload_video(file_path: str, title: str, description: str = "", tags: list = None, user_id: str = "default") -> dict:
    """Upload video to YouTube using OAuth token.
    
    Args:
        file_path: Path to video file
        title: Video title
        description: Video description
        tags: List of tags (optional)
        user_id: User identifier for token lookup
        
    Returns:
        YouTube API response with video ID
    """
    token_path = os.path.join(TOKENS_DIR, f"{user_id}.json")
    
    if not os.path.exists(token_path):
        raise FileNotFoundError(f"Token not found for user {user_id}. Visit /auth/connect first to authenticate.")
    
    creds = Credentials.from_authorized_user_file(token_path)
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
