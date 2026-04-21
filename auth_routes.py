from fastapi import APIRouter
from fastapi.responses import RedirectResponse
from google_auth_oauthlib.flow import Flow
import os
import json

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

STATE_FILE = "oauth_state.json"
TOKEN_FILE = "user_token.json"


# 🔹 STEP 1: CONNECT
@router.get("/auth/connect")
def connect():
    try:
        if not client_config:
            return {"error": "GOOGLE_CLIENT_SECRET not set and no client_secret.json found"}

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

        # ✅ store state AND code_verifier (PKCE requirement)
        with open(STATE_FILE, "w") as f:
            json.dump({
                "state": state,
                "code_verifier": flow.code_verifier
            }, f)

        return RedirectResponse(auth_url)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": str(e)}


# 🔹 STEP 2: CALLBACK
@router.get("/auth/callback")
def callback(code: str, state: str):

    if not os.path.exists(STATE_FILE):
        return {"error": "State missing. Restart auth."}

    saved_data = json.load(open(STATE_FILE))
    saved_state = saved_data["state"]
    code_verifier = saved_data.get("code_verifier")

    if state != saved_state:
        return {"error": "State mismatch"}

    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        state=saved_state,
        redirect_uri=REDIRECT_URI
    )
    
    # 🔥 Restore code_verifier for PKCE
    if code_verifier:
        flow.code_verifier = code_verifier

    flow.fetch_token(code=code)

    creds = flow.credentials

    with open(TOKEN_FILE, "w") as f:
        f.write(creds.to_json())

    os.remove(STATE_FILE)

    # Redirect back to frontend settings page
    return RedirectResponse("http://localhost:3000/settings")


# 🔹 STEP 3: STATUS
@router.get("/auth/status")
def status():
    return {"connected": os.path.exists(TOKEN_FILE)}