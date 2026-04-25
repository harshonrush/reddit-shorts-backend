import os
from supabase import create_client

def get_supabase():
    """Initialize Supabase client - fails fast if config missing."""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_KEY")

    if not url or not key:
        raise RuntimeError(
            " Supabase env variables missing. Cannot start server.\n"
            f"SUPABASE_URL: {'set' if url else 'missing'}\n"
            f"SUPABASE_KEY: {'set' if key else 'missing'}"
        )

    return create_client(url, key)

supabase = get_supabase()
print("[DB] Supabase connected")