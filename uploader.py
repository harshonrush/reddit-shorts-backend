from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
import os


def upload_video(file_path: str, title: str, description: str = "", tags: list = None) -> dict:
    """Upload video to YouTube using OAuth token.
    
    Args:
        file_path: Path to video file
        title: Video title
        description: Video description
        tags: List of tags (optional)
        
    Returns:
        YouTube API response with video ID
    """
    if not os.path.exists("user_token.json"):
        raise FileNotFoundError("user_token.json not found. Visit http://localhost:8000/auth/connect first to authenticate.")
    
    creds = Credentials.from_authorized_user_file("user_token.json")
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
