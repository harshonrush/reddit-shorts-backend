import runpod
import sys

def handler(job):
    """Minimal handler with error handling and timeout safety."""
    try:
        # Log to stderr (shows in RunPod logs)
        print("[HANDLER] Job received", file=sys.stderr)
        
        # Quick response - don't process anything yet
        return {
            "status": "success",
            "message": "Handler is working"
        }
    except Exception as e:
        print(f"[HANDLER ERROR] {e}", file=sys.stderr)
        return {
            "status": "error",
            "message": str(e)
        }

runpod.serverless.start({"handler": handler})
