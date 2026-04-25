import os


def validate_env():
    """Validate all required environment variables on startup."""
    required = [
        "REDIS_URL",
        "SUPABASE_URL",
        "SUPABASE_KEY"
    ]

    missing = []
    for key in required:
        if not os.getenv(key):
            missing.append(key)

    if missing:
        raise RuntimeError(
            f"\n❌ Missing required environment variables:\n" +
            "\n".join([f"   - {k}" for k in missing]) +
            "\n\nSet these in Railway dashboard and restart service."
        )

    print("✅ All environment variables validated")
