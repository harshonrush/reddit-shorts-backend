from fastapi import APIRouter, Query
from fastapi.responses import RedirectResponse
from google_auth_oauthlib.flow import Flow
import os
import json
import uuid
from db import supabase
from redis_queue import redis_conn

router = APIRouter()

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

# Load client secret from environment variable
client_config = None
if os.getenv("GOOGLE_CLIENT_SECRET"):
    client_config = json.loads(os.getenv("GOOGLE_CLIENT_SECRET"))
else:
    # Fallback: look for client_secret file
    for f in os.listdir("."):
        if f.startswith("client_secret") and f.endswith(".json"):
            with open(f) as file:
                client_config = json.load(file)
            break

REDIRECT_URI = "https://reddit-shorts-backend-production.up.railway.app/auth/callback"
TOKENS_DIR = "tokens"
os.makedirs(TOKENS_DIR, exist_ok=True)


def get_token_path(user_id: str):
    """Get token file path for a user."""
    return os.path.join(TOKENS_DIR, f"{user_id}.json")


# 🔹 STEP 1: CONNECT
@router.get("/auth/connect")
def connect(user_id: str = Query(None)):
    try:
        if not client_config:
            return {"error": "GOOGLE_CLIENT_SECRET not set and no client_secret.json found"}

        # Generate user_id if not provided
        if not user_id:
            user_id = str(uuid.uuid4())

        flow = Flow.from_client_config(
            client_config,
            scopes=SCOPES,
            redirect_uri=REDIRECT_URI
        )

        # 🔥 IMPORTANT: FORCE CONSISTENT STATE
        auth_url, state = flow.authorization_url(
            access_type="offline",
            prompt="consent",
            include_granted_scopes="true"
        )

        # ✅ Store state in Redis (multi-user safe, 10-min TTL)
        redis_conn.set(
            f"oauth_state:{state}",
            json.dumps({
                "state": state,
                "code_verifier": flow.code_verifier,
                "user_id": user_id
            }),
            ex=600  # 10 minutes
        )

        # Return auth URL with user_id for frontend
        return {"auth_url": auth_url, "user_id": user_id}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": str(e)}


# 🔹 STEP 2: CALLBACK
@router.get("/auth/callback")
def callback(code: str, state: str):
    print(f"[AUTH CALLBACK] Received callback with state={state[:20]}... code={code[:20]}...")
    
    # Check client config
    if not client_config:
        print("[AUTH ERROR] GOOGLE_CLIENT_SECRET not configured")
        return {"error": "Server configuration error: GOOGLE_CLIENT_SECRET not set"}

    # Retrieve state from Redis (multi-user safe)
    raw_state = redis_conn.get(f"oauth_state:{state}")
    if not raw_state:
        print("[AUTH ERROR] State not found in Redis (expired or missing)")
        return {"error": "State expired or missing. Restart auth."}

    try:
        saved_data = json.loads(raw_state if isinstance(raw_state, str) else raw_state.decode("utf-8"))
    except Exception as e:
        print(f"[AUTH ERROR] Failed to parse state data: {e}")
        return {"error": f"Failed to load state: {str(e)}"}
        
    saved_state = saved_data.get("state")
    code_verifier = saved_data.get("code_verifier")
    user_id = saved_data.get("user_id", "default")
    
    print(f"[AUTH CALLBACK] Saved state={saved_state[:20] if saved_state else None}... user_id={user_id}")

    if state != saved_state:
        print(f"[AUTH ERROR] State mismatch: received={state[:20]}... vs saved={saved_state[:20] if saved_state else None}...")
        return {"error": "State mismatch - possible CSRF attack"}

    try:
        flow = Flow.from_client_config(
            client_config,
            scopes=SCOPES,
            state=saved_state,
            redirect_uri=REDIRECT_URI
        )
        
        # 🔥 Restore code_verifier for PKCE
        if code_verifier:
            flow.code_verifier = code_verifier
            print(f"[AUTH CALLBACK] Restored code_verifier")

        print(f"[AUTH CALLBACK] Fetching token...")
        flow.fetch_token(code=code)
        print(f"[AUTH CALLBACK] Token fetched successfully")

        creds = flow.credentials
        
        if not creds.token:
            print("[AUTH ERROR] No access token in credentials")
            return {"error": "Failed to get access token from Google"}

        print(f"[AUTH CALLBACK] Saving token for user {user_id}")
        
        # First ensure user exists in users_settings (foreign key requirement)
        try:
            from scheduler import load_settings
            load_settings(user_id)  # This creates default row if not exists
            print(f"[AUTH CALLBACK] Ensured user row exists in users_settings")
        except Exception as e:
            print(f"[AUTH WARNING] Could not create user settings row: {e}")
        
        # Save token to Supabase
        result = supabase.table("user_tokens").upsert({
            "user_id": user_id,
            "access_token": creds.token,
            "refresh_token": creds.refresh_token,
            "expiry": creds.expiry.isoformat() if creds.expiry else None
        }, on_conflict="user_id").execute()
        print(f"[AUTH CALLBACK] Token saved to Supabase: {result}")

        redis_conn.delete(f"oauth_state:{state}")
        print(f"[AUTH CALLBACK] State file cleaned up, redirecting to dashboard")

        # Redirect back to frontend dashboard after auth
        FRONTEND_URL = "https://reddit-shorts-frontend.vercel.app/dashboard"
        return RedirectResponse(FRONTEND_URL)
        
    except Exception as e:
        import traceback
        print(f"[AUTH ERROR] Exception in callback: {e}")
        traceback.print_exc()
        return {"error": f"OAuth callback failed: {str(e)}"}


# 🔹 STEP 3: STATUS
@router.get("/auth/status")
def status(user_id: str = Query("default")):
    connected = False
    yt_connected = False
    tt_connected = False
    ig_connected = False
    
    try:
        res = supabase.table("user_tokens").select("*").eq("user_id", user_id).execute()
        if res.data:
            token_data = res.data[0]
            yt_connected = bool(token_data.get("access_token"))
            tt_connected = bool(token_data.get("tiktok_access_token"))
            ig_connected = bool(token_data.get("instagram_access_token"))
            connected = yt_connected or tt_connected or ig_connected
    except Exception as e:
        print(f"[AUTH STATUS ERROR] Failed to query user tokens: {e}")

    return {
        "connected": connected,
        "yt_connected": yt_connected,
        "tt_connected": tt_connected,
        "ig_connected": ig_connected,
        "user_id": user_id
    }


# 🔹 STEP 4: TIKTOK CONNECT & CALLBACK (OAuth Gateway & Simulator)
@router.get("/auth/connect/tiktok")
def connect_tiktok(user_id: str = Query(None)):
    """Initiates TikTok connection workflow."""
    if not user_id:
        user_id = str(uuid.uuid4())
    
    # Standard redirect callback url back to settings dashboard page
    FRONTEND_REDIRECT = f"http://localhost:3000/settings?user_id={user_id}&tiktok=connected"
    
    # In live API integration, we build standard authorization_url.
    # To facilitate high-fidelity sandbox mock connect immediately:
    # Save simulated TikTok access token in user_tokens database:
    try:
        # Ensure default rows exists
        try:
            from scheduler import load_settings
            load_settings(user_id)
        except Exception:
            pass
            
        supabase.table("user_tokens").upsert({
            "user_id": user_id,
            "tiktok_access_token": "mock_tiktok_token_simulated_credentials",
            "tiktok_refresh_token": "mock_tiktok_refresh_simulated",
            "tiktok_expiry": None
        }, on_conflict="user_id").execute()
        print(f"[TIKTOK CONNECT] Simulated credentials linked successfully for User: {user_id}")
    except Exception as e:
        print(f"[TIKTOK CONNECT ERROR] Failed to link mock credentials: {e}")
        
    return {"auth_url": FRONTEND_REDIRECT, "user_id": user_id}


# 🔹 STEP 5: INSTAGRAM CONNECT & CALLBACK (OAuth Gateway & Simulator)
@router.get("/auth/connect/instagram")
def connect_instagram(user_id: str = Query(None)):
    """Initiates Instagram connection workflow."""
    if not user_id:
        user_id = str(uuid.uuid4())
        
    FRONTEND_REDIRECT = f"http://localhost:3000/settings?user_id={user_id}&instagram=connected"
    
    try:
        try:
            from scheduler import load_settings
            load_settings(user_id)
        except Exception:
            pass
            
        supabase.table("user_tokens").upsert({
            "user_id": user_id,
            "instagram_access_token": "mock_instagram_token_simulated_credentials",
            "instagram_expiry": None
        }, on_conflict="user_id").execute()
        print(f"[INSTAGRAM CONNECT] Simulated credentials linked successfully for User: {user_id}")
    except Exception as e:
        print(f"[INSTAGRAM CONNECT ERROR] Failed to link mock credentials: {e}")
        
    return {"auth_url": FRONTEND_REDIRECT, "user_id": user_id}