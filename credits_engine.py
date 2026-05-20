import json
import sys
from db import supabase
from redis_queue import redis_conn

DEFAULT_FREE_CREDITS = 5
TIER_CREDITS = {
    "free": 5,
    "starter": 30,
    "pro": 100
}

def get_user_credits(user_id: str) -> dict:
    """Retrieve credits balance and tier details for a user.
    
    Tries Supabase first, falls back to Redis in-memory storage.
    
    Returns:
        dict: {"user_id": str, "credits_remaining": int, "tier": str}
    """
    if not user_id or user_id == "default":
        # System-wide testing default
        return {"user_id": "default", "credits_remaining": 9999, "tier": "pro"}

    # 1. Try Supabase
    try:
        res = supabase.table("user_credits").select("*").eq("user_id", user_id).execute()
        if res.data:
            return {
                "user_id": user_id,
                "credits_remaining": int(res.data[0].get("credits_remaining", DEFAULT_FREE_CREDITS)),
                "tier": res.data[0].get("tier", "free")
            }
    except Exception as e:
        print(f"[CREDITS ENGINE] Supabase credits query error: {e}. Falling back to Redis.", file=sys.stderr)

    # 2. Redis Fallback
    redis_key = f"credits:{user_id}"
    cached_data = redis_conn.get(redis_key)
    if cached_data:
        try:
            return json.loads(cached_data.decode("utf-8"))
        except Exception:
            pass

    # 3. Create default credits for new user
    default_credits = {
        "user_id": user_id,
        "credits_remaining": DEFAULT_FREE_CREDITS,
        "tier": "free"
    }

    # Try saving default back to Supabase
    try:
        supabase.table("user_credits").upsert(default_credits).execute()
        return default_credits
    except Exception:
        # Fallback to Redis cache only
        redis_conn.set(redis_key, json.dumps(default_credits), ex=604800) # 1 week TTL
        return default_credits


def deduct_user_credits(user_id: str, amount: int = 1) -> bool:
    """Deduct standard amount from user credits balance.
    
    Returns:
        bool: True if successfully deducted, False if insufficient credits.
    """
    if not user_id or user_id == "default":
        return True

    balance_info = get_user_credits(user_id)
    current_credits = balance_info.get("credits_remaining", 0)

    if current_credits < amount:
        print(f"[CREDITS ENGINE] User {user_id} has insufficient credits: {current_credits} < {amount}", file=sys.stderr)
        return False

    new_credits = current_credits - amount
    balance_info["credits_remaining"] = new_credits

    # Save to Supabase
    saved_supabase = False
    try:
        supabase.table("user_credits").update({
            "credits_remaining": new_credits
        }).eq("user_id", user_id).execute()
        saved_supabase = True
    except Exception as e:
        print(f"[CREDITS ENGINE] Supabase credits update error: {e}", file=sys.stderr)

    # Save to Redis
    redis_key = f"credits:{user_id}"
    redis_conn.set(redis_key, json.dumps(balance_info), ex=604800)
    print(f"[CREDITS ENGINE] Deducted {amount} credit from user {user_id}. Remaining: {new_credits}", file=sys.stderr)
    return True


def add_user_credits(user_id: str, amount: int, tier: str = None) -> dict:
    """Add credits to a user balance and optionally update their subscription tier."""
    if not user_id or user_id == "default":
        return {"user_id": "default", "credits_remaining": 9999, "tier": "pro"}

    balance_info = get_user_credits(user_id)
    new_credits = balance_info.get("credits_remaining", 0) + amount
    
    balance_info["credits_remaining"] = new_credits
    if tier:
        balance_info["tier"] = tier

    # Save to Supabase
    try:
        supabase.table("user_credits").upsert(balance_info).execute()
    except Exception as e:
        print(f"[CREDITS ENGINE] Supabase credits add error: {e}", file=sys.stderr)

    # Save to Redis
    redis_key = f"credits:{user_id}"
    redis_conn.set(redis_key, json.dumps(balance_info), ex=604800)
    print(f"[CREDITS ENGINE] Added {amount} credits to user {user_id}. New balance: {new_credits}, Tier: {balance_info['tier']}", file=sys.stderr)
    return balance_info
