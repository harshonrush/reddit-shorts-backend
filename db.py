import os
from supabase import create_client

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("[DB] WARNING: Missing Supabase env variables. Worker may fail.")
    print(f"[DB] SUPABASE_URL: {'set' if SUPABASE_URL else 'missing'}")
    print(f"[DB] SUPABASE_KEY: {'set' if SUPABASE_KEY else 'missing'}")
    # Create a dummy client that will fail gracefully
    supabase = None
else:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("[DB] Supabase client initialized successfully")
    except Exception as e:
        print(f"[DB] ERROR initializing Supabase: {e}")
        supabase = None