import runpod

def handler(job):
    return {"status": "working"}

runpod.serverless.start({"handler": handler})
