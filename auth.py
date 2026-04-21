"""YouTube OAuth authentication - Run ONCE to get token.json"""
from google_auth_oauthlib.flow import InstalledAppFlow
import os

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

# Find client secret file (downloaded from Google Cloud Console)
CLIENT_SECRET_FILE = None
for f in os.listdir("."):
    if f.startswith("client_secret") and f.endswith(".json"):
        CLIENT_SECRET_FILE = f
        break

def authenticate():
    if not CLIENT_SECRET_FILE:
        print("❌ client_secret file not found. Download it from Google Cloud Console.")
        return
    
    print(f"Using: {CLIENT_SECRET_FILE}")
    
    flow = InstalledAppFlow.from_client_secrets_file(
        CLIENT_SECRET_FILE,
        SCOPES
    )
    creds = flow.run_local_server(port=0)

    with open("token.json", "w") as token:
        token.write(creds.to_json())

    print("✅ YouTube connected - token.json saved")

if __name__ == "__main__":
    authenticate()
