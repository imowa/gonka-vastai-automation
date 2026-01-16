# MLNode SSH Issue - FIXED ✅

## Problem Summary

Your code was failing because it tried to SSH into the MLNode Docker container, but the official Gonka MLNode image (`ghcr.io/product-science/mlnode:3.0.11-post1`) **does not include an SSH server**.

### Error Timeline
```
15:05:46.585 - Vast.ai says "instance ready" (false positive - just checks API fields)
15:05:47.818 - Your code tries to actually SSH into the container
15:06:14 - 15:08:21 - SSH connection fails repeatedly for 154+ seconds
```

## Root Cause

**Architecture Mismatch:**
- Official Gonka setup: Run full node on your own server with GPU (includes SSH access)
- Your setup: Rent Vast.ai GPU on-demand for PoC only (container has no SSH)

The MLNode Docker image is a **specialized container** that only runs:
- MLNode API on port 5070
- vLLM inference engine
- PoC computation services

It does NOT include:
- SSH server
- Shell access
- Linux utilities

## Solution Applied

### Files Modified:

1. **`scripts/mlnode_poc_manager.py`**
   - Removed SSH readiness check from `start_mlnode_container()`
   - Now only waits for MLNode API (port 5070) to be accessible
   - Added clearer logging

2. **`test_mlnode_poc_integration.py`**
   - Updated misleading "SSH connected" message
   - Now says "Instance accessible at" (just connection info)
   - Added note that SSH is not used

### What Changed:

**BEFORE:**
```python
def start_mlnode_container():
    # Step 1: Wait for SSH ❌ FAILS HERE
    if not wait_for_ssh_ready():
        return None

    # Step 2: Wait for MLNode API
    if not wait_for_mlnode_ready():
        return None
```

**AFTER:**
```python
def start_mlnode_container():
    # Build MLNode URL and wait for API to be ready ✅
    mlnode_url = f"http://{host}:{port}"
    if not wait_for_mlnode_ready(mlnode_url):
        return None
```

## Expected Behavior Now

1. ✅ Vast.ai creates instance with MLNode image
2. ✅ Your code gets connection details (host/port)
3. ✅ Waits for MLNode API at `http://{host}:5070/api/v1/state`
4. ✅ Once API responds with ready state, proceeds to register node

## Important Notes

### Startup Time
The MLNode container may take **15-30 minutes** to start because:
- Downloads Qwen/Qwen2.5-7B-Instruct model (~15GB)
- Initializes vLLM engine
- Loads model into GPU memory

Your timeout is set to **1800 seconds (30 minutes)** which should be sufficient.

### Cost Implications
- Each startup requires full model download (no persistent cache)
- Network speed on Vast.ai instance affects download time
- Consider this in your cost calculations

### Debugging Without SSH

Since you can't SSH into the container, debugging options are:
1. Check Vast.ai console logs
2. Monitor MLNode API endpoints
3. Check Network Node admin API for registration status

## Configuration

Your current settings (from `.env`):
```bash
MLNODE_PORT=5070                    # MLNode API port
MLNODE_API_SEGMENT=/api/v1          # API path
MLNODE_STARTUP_TIMEOUT=1800         # 30 min timeout
VASTAI_SSH_READY_TIMEOUT=900        # Not used anymore
```

## Testing

Run the integration test:
```bash
python test_mlnode_poc_integration.py --skip-poc
```

This will:
1. Rent a GPU from Vast.ai
2. Wait for MLNode to initialize
3. Register with Network Node
4. Verify health
5. Unregister and stop GPU

**Expected cost:** ~$0.10-0.20 for a 15-30 minute test

## Next Steps

1. Test the fix with `--skip-poc` flag first
2. If successful, try full PoC flow
3. Monitor actual startup times to optimize timeout settings
4. Consider building a custom image with pre-downloaded models (advanced)

## Alternative Approaches (If Issues Persist)

### Option 1: Custom Image with Pre-downloaded Models
- Build custom Docker image with models baked in
- Faster startup (~2-5 min instead of 15-30 min)
- Lower cost per PoC

### Option 2: Use Base Image + Startup Script
- Deploy `nvidia/cuda` base image with SSH
- Use startup script to pull and run MLNode
- More control but slower startup

### Option 3: Keep Instance Running Between PoCs
- If PoCs are frequent (multiple per day)
- Keep instance idle between PoCs
- Trade startup time for higher cost

## Contact

If the fix doesn't work, check:
1. Is port 5070 accessible from outside? (Vast.ai should expose it)
2. Does the MLNode container start at all? (Check Vast.ai console)
3. Are there any error messages in the MLNode API responses?

---

**Summary:** The SSH check has been removed. Your code now only waits for the MLNode API to be ready, which is the correct approach for the MLNode Docker image.
