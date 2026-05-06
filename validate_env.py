import os


def validate_env():
    """Validate environment variables based on environment."""
    # RunPod doesn't need Supabase - it only renders video
    if os.getenv("RUNPOD_ENV") == "true":
        print("[ENV] RunPod environment - skipping Supabase validation")
        return

    # Railway needs Supabase for DB operations
    required = ["REDIS_URL", "SUPABASE_URL", "SUPABASE_KEY"]
    optional = ["GEMINI_API_KEY"]  # Fallback TTS

    missing = [v for v in required if not os.getenv(v)]

    if missing:
        raise RuntimeError(f"Missing env vars: {missing}")

    # Check optional vars
    for var in optional:
        if not os.getenv(var):
            print(f"⚠️  Optional {var} not set - fallback features may not work")

    print("✅ Railway environment validated")
