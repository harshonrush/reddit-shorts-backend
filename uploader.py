from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from datetime import datetime, timedelta, timezone
import os
import json
import tempfile
import requests
from db import supabase


def _get_redis_lock(lock_key: str, ttl: int = 60) -> bool:
    """Try to acquire Redis lock. Returns True if acquired."""
    try:
        from redis_queue import redis_conn
        # NX=True: only set if not exists (atomic)
        acquired = redis_conn.set(lock_key, "1", nx=True, ex=ttl)
        return bool(acquired)
    except Exception as e:
        print(f"[TOKEN LOCK] Redis error: {e}")
        return False  # Fail to acquire lock if Redis is down (safer)


def _release_redis_lock(lock_key: str):
    """Release Redis lock."""
    try:
        from redis_queue import redis_conn
        redis_conn.delete(lock_key)
    except Exception as e:
        print(f"[TOKEN LOCK] Failed to release lock: {e}")


def _parse_expiry(expiry_str) -> datetime:
    """Parse expiry string to timezone-aware datetime."""
    if not expiry_str:
        return None
    
    if isinstance(expiry_str, datetime):
        expiry = expiry_str
    else:
        expiry = datetime.fromisoformat(expiry_str)
    
    # Make timezone-aware (assume UTC if no timezone)
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    
    return expiry


def get_google_oauth_credentials():
    """Extract client_id and client_secret from environment.
    
    Handles two formats:
    1. GOOGLE_CLIENT_SECRET as full JSON config (same as client_secret.json)
    2. Separate GOOGLE_CLIENT_ID + GOOGLE_CLIENT_SECRET env vars
    
    Returns:
        tuple: (client_id, client_secret)
    """
    raw = os.getenv("GOOGLE_CLIENT_SECRET", "")
    
    # Try parsing as JSON config (the full client_secret.json format)
    if raw.strip().startswith("{"):
        try:
            config = json.loads(raw)
            # Handle {"web": {...}} or {"installed": {...}} format
            inner = config.get("web") or config.get("installed") or {}
            cid = inner.get("client_id", "")
            csec = inner.get("client_secret", "")
            if cid and csec:
                return cid, csec
        except json.JSONDecodeError:
            pass
    
    # Fallback: separate env vars
    return os.getenv("GOOGLE_CLIENT_ID", ""), raw


def refresh_token_if_needed(creds: Credentials, user_id: str, old_refresh_token: str = None) -> Credentials:
    """Refresh access token if expired or about to expire (with 5-min buffer).
    
    Args:
        creds: Google OAuth credentials
        user_id: User identifier
        old_refresh_token: Original refresh token (to preserve if Google returns None)
    
    Returns:
        Updated credentials
    """
    # Validate user_id is a proper UUID, not "default" or empty
    if not user_id or user_id == "default":
        raise ValueError(f"Invalid user_id: {user_id!r}. Must be a valid UUID.")
    
    if not creds:
        return creds
    
    # Handle expiry - creds.expiry is already a datetime object
    expiry = creds.expiry
    if expiry and expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    
    now = datetime.now(timezone.utc)
    
    # Check if refresh needed (5-minute buffer before expiry)
    needs_refresh = False
    if expiry:
        buffer_time = expiry - timedelta(minutes=5)
        needs_refresh = buffer_time <= now
    else:
        needs_refresh = True  # No expiry = assume expired
    
    print(f"[TOKEN DEBUG] user_id={user_id}")
    print(f"[TOKEN DEBUG] expiry={expiry}")
    print(f"[TOKEN DEBUG] now={now}")
    print(f"[TOKEN DEBUG] needs_refresh={needs_refresh}")
    print(f"[TOKEN DEBUG] has_refresh_token={bool(creds.refresh_token)}")
    
    if not needs_refresh:
        print("[TOKEN] Token still valid, no refresh needed")
        return creds
    
    if not creds.refresh_token:
        print("[TOKEN ERROR] No refresh token available!")
        return creds
    
    # Try to acquire Redis lock to prevent concurrent refreshes
    lock_key = f"token_refresh:{user_id}"
    if not _get_redis_lock(lock_key, ttl=60):
        print("[TOKEN LOCK] Another process is refreshing this token, waiting...")
        import time
        time.sleep(2)  # Wait for other process to complete
        # Re-fetch token from DB (other process should have updated it)
        return load_credentials_from_supabase(user_id)
    
    try:
        print("[TOKEN] Refreshing access token...")
        creds.refresh(Request())
        print(f"[TOKEN] Refresh successful!")
        token_preview = creds.token[:20] if creds.token else "None"
        print(f"[TOKEN DEBUG] new_token={token_preview}...")
        print(f"[TOKEN DEBUG] new_expiry={creds.expiry}")
        
        # IMPORTANT: Google may return refresh_token=None on refresh
        # Never overwrite DB with null - keep the old refresh token
        final_refresh_token = creds.refresh_token or old_refresh_token
        print(f"[TOKEN DEBUG] refresh_token_preserved={bool(creds.refresh_token is None and old_refresh_token)}")
        
        # Save updated tokens to DB
        update_data = {
            "access_token": creds.token,
            "expiry": creds.expiry.isoformat() if creds.expiry else None
        }
        if final_refresh_token:
            update_data["refresh_token"] = final_refresh_token
        
        result = supabase.table("user_tokens").update(update_data).eq("user_id", user_id).execute()
        print(f"[TOKEN] Saved refreshed tokens to DB: {result.data}")
        
    except Exception as e:
        print(f"[TOKEN ERROR] Refresh failed: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        _release_redis_lock(lock_key)
    
    return creds


def load_credentials_from_supabase(user_id: str) -> Credentials:
    """Load YouTube credentials from Supabase user_tokens table."""
    res = supabase.table("user_tokens").select("*").eq("user_id", user_id).execute()
    
    if not res.data:
        raise FileNotFoundError(f"Token not found for user {user_id}. Visit /auth/connect first to authenticate.")
    
    token_data = res.data[0]
    
    # Parse expiry with proper timezone handling
    expiry = _parse_expiry(token_data.get("expiry"))
    old_refresh_token = token_data.get("refresh_token")
    
    client_id, client_secret = get_google_oauth_credentials()
    
    creds = Credentials(
        token=token_data["access_token"],
        refresh_token=old_refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=["https://www.googleapis.com/auth/youtube.upload"],
        expiry=expiry
    )
    
    # Debug log
    print(f"[UPLOADER DEBUG] load_credentials client_id: {client_id[:20]}...")
    
    # Use unified refresh function with Redis lock and proper token preservation
    creds = refresh_token_if_needed(creds, user_id, old_refresh_token)
    
    return creds


def upload_video(video_url: str = None, file_path: str = None, title: str = "", description: str = "", tags: list = None, user_id: str = None, token_data: dict = None) -> dict:
    """Upload video to YouTube using OAuth token.
    
    Args:
        video_url: URL to video file (downloaded before upload)
        file_path: Path to local video file (alternative to URL)
        title: Video title
        description: Video description
        tags: List of tags (optional)
        user_id: User identifier for token lookup (REQUIRED)
        token_data: Pre-fetched token data (optional, saves DB query)
        
    Returns:
        YouTube API response with video ID
    """
    # Validate user_id is provided and not "default"
    if not user_id:
        raise ValueError("user_id is required for upload_video")
    if user_id == "default":
        raise ValueError("user_id cannot be 'default' - must be a valid UUID")
    
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
    client_id, client_secret = get_google_oauth_credentials()
    print(f"[UPLOADER DEBUG] GOOGLE_CLIENT_ID: {client_id[:20]}...")
    print(f"[UPLOADER DEBUG] GOOGLE_CLIENT_SECRET set: {bool(client_secret)}")
    
    if token_data:
        # Use pre-fetched token (saves DB query)
        # Parse expiry with proper timezone handling
        expiry = _parse_expiry(token_data.get("expiry"))

        old_refresh_token = token_data.get("refresh_token")
        creds = Credentials(
            token=token_data["access_token"],
            refresh_token=old_refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
            scopes=["https://www.googleapis.com/auth/youtube.upload"],
            expiry=expiry
        )
        # Refresh if needed (pass old_refresh_token to preserve it)
        creds = refresh_token_if_needed(creds, user_id, old_refresh_token)
    else:
        # Fallback: fetch from DB
        creds = load_credentials_from_supabase(user_id)

    print("[UPLOADER] STEP 2: Building YouTube API client...")
    youtube = build("youtube", "v3", credentials=creds)

    if tags is None:
        tags = ["shorts", "reddit", "story"]

    # Track all temp files for cleanup
    temp_files = []
    if downloaded:
        temp_files.append(file_path)

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
        media_body=MediaFileUpload(file_path, chunksize=1024*1024, resumable=True)  # 1MB chunks
    )

    print("[UPLOADER] STEP 4: Sending to YouTube API (with retry)...")
    
    # Retry logic for YouTube API
    max_retries = 3
    last_error = None
    
    for attempt in range(max_retries):
        try:
            print(f"[UPLOADER] Upload attempt {attempt + 1}/{max_retries}...")
            
            # Chunked upload with progress tracking
            response = None
            retry_count = 0
            max_upload_retries = 100  # Prevent infinite loops
            
            while response is None and retry_count < max_upload_retries:
                status, response = request.next_chunk()
                if status:
                    print(f"[UPLOADER] Upload progress: {int(status.progress() * 100)}%")
                retry_count += 1
            
            if response is None:
                raise Exception("Upload failed: response is None after all chunks")
            
            print(f"[UPLOADER] STEP 5: Upload response received: {response}")
            print(f"✅ Uploaded to YouTube: https://youtube.com/watch?v={response['id']}")
            
            # Cleanup temp files on success
            for temp_file in temp_files:
                if os.path.exists(temp_file):
                    try:
                        os.unlink(temp_file)
                        print(f"[UPLOADER] Cleaned up temp file: {temp_file}")
                    except Exception as e:
                        print(f"[UPLOADER] Failed to cleanup temp file: {e}")
            
            return response
            
        except Exception as e:
            last_error = e
            print(f"[UPLOADER ERROR] Attempt {attempt + 1} failed: {e}")
            
            if attempt < max_retries - 1:
                import time
                wait_time = 2 ** attempt  # Exponential backoff: 1, 2, 4 seconds
                print(f"[UPLOADER] Retrying in {wait_time}s...")
                time.sleep(wait_time)
                # Recreate the request for retry
                request = youtube.videos().insert(
                    part="snippet,status",
                    body={
                        "snippet": {
                            "title": title,
                            "description": description,
                            "tags": tags,
                            "categoryId": "22"
                        },
                        "status": {
                            "privacyStatus": "public"
                        }
                    },
                    media_body=MediaFileUpload(file_path, chunksize=1024*1024, resumable=True)
                )
    
    # All retries failed - cleanup and raise
    print(f"[UPLOADER ERROR] All {max_retries} upload attempts failed")
    
    for temp_file in temp_files:
        if os.path.exists(temp_file):
            try:
                os.unlink(temp_file)
                print(f"[UPLOADER] Cleaned up temp file: {temp_file}")
            except Exception as e:
                print(f"[UPLOADER] Failed to cleanup temp file: {e}")
    
    raise last_error if last_error else Exception("Upload failed after all retries")


def trigger_auto_publish(video_url: str, title: str, user_id: str):
    """Publish finished short video in parallel to connected social platforms in the background."""
    import threading
    
    def worker():
        print(f"[AUTO PUBLISH] Beginning publishing run for User: {user_id} | Title: {title}", file=sys.stderr)
        
        # Load user tokens
        token_data = None
        try:
            res = supabase.table("user_tokens").select("*").eq("user_id", user_id).execute()
            if res.data:
                token_data = res.data[0]
        except Exception as e:
            print(f"[AUTO PUBLISH ERROR] Failed to query user tokens: {e}", file=sys.stderr)
            return

        if not token_data:
            print(f"[AUTO PUBLISH] No active social tokens connected for User: {user_id}", file=sys.stderr)
            return

        # 1. YouTube Upload
        if token_data.get("access_token"):
            try:
                print("[AUTO PUBLISH] Triggering YouTube upload...", file=sys.stderr)
                upload_video(
                    video_url=video_url,
                    title=f"{title.title()} Story",
                    description=f"{title}\n\n#shorts #reddit #viral",
                    token_data=token_data,
                    user_id=user_id
                )
            except Exception as e:
                print(f"[AUTO PUBLISH ERROR] YouTube upload failed: {e}", file=sys.stderr)

        # 2. TikTok Upload
        if token_data.get("tiktok_access_token"):
            try:
                from tiktok_uploader import upload_to_tiktok
                print("[AUTO PUBLISH] Triggering TikTok upload...", file=sys.stderr)
                upload_to_tiktok(
                    video_url=video_url,
                    title=f"{title.title()} Story #shorts #viral",
                    user_id=user_id
                )
            except Exception as e:
                print(f"[AUTO PUBLISH ERROR] TikTok upload failed: {e}", file=sys.stderr)

        # 3. Instagram Reels Upload
        if token_data.get("instagram_access_token"):
            try:
                from instagram_uploader import upload_to_instagram
                print("[AUTO PUBLISH] Triggering Instagram upload...", file=sys.stderr)
                upload_to_instagram(
                    video_url=video_url,
                    caption=f"{title.title()} Story #reels #viral",
                    user_id=user_id
                )
            except Exception as e:
                print(f"[AUTO PUBLISH ERROR] Instagram upload failed: {e}", file=sys.stderr)
                
    # Spawn background thread to keep it lightweight and fast
    thread = threading.Thread(target=worker)
    thread.daemon = True
    thread.start()
    print(f"[AUTO PUBLISH] Started publishing background thread for User: {user_id}", file=sys.stderr)

