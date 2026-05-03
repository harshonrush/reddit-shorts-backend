from fastapi import APIRouter, Query
from fastapi.responses import RedirectResponse
from google_auth_oauthlib.flow import Flow
import os
import json
import uuid
from db import supabase

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

STATE_FILE = "oauth_state.json"


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

        # ✅ store state AND code_verifier (PKCE requirement) + user_id
        with open(STATE_FILE, "w") as f:
            json.dump({
                "state": state,
                "code_verifier": flow.code_verifier,
                "user_id": user_id
            }, f)

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

    if not os.path.exists(STATE_FILE):
        print("[AUTH ERROR] State file missing")
        return {"error": "State missing. Restart auth."}

    try:
        saved_data = json.load(open(STATE_FILE))
    except Exception as e:
        print(f"[AUTH ERROR] Failed to load state file: {e}")
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
        # Save token to Supabase
        result = supabase.table("user_tokens").upsert({
            "user_id": user_id,
            "access_token": creds.token,
            "refresh_token": creds.refresh_token,
            "expiry": creds.expiry.isoformat() if creds.expiry else None
        }, on_conflict="user_id").execute()
        print(f"[AUTH CALLBACK] Token saved to Supabase: {result}")

        os.remove(STATE_FILE)
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
    res = supabase.table("user_tokens").select("*").eq("user_id", user_id).execute()
    return {"connected": len(res.data) > 0, "user_id": user_id}