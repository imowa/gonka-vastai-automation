# MLNode Port Configuration - CORRECTED ✅

## The Problem

We were trying to expose port **5070** on Vast.ai, but the official MLNode Docker image actually runs on port **8080**, not 5070!

## Discovery

After analyzing the official Gonka deployment scripts from [ezlabsnodes/gonka](https://github.com/ezlabsnodes/gonka), we found:

### Official MLNode Configuration

From the [docker-compose.mlnode.yml](https://github.com/gonka-ai/gonka/blob/312044d28c7170d7f08bf88e41427396f3b95817/deploy/join/docker-compose.mlnode.yml):

```yaml
services:
  mlnode-308:
    image: ghcr.io/product-science/mlnode:3.0.9
    command: uvicorn api.app:app --host=0.0.0.0 --port=8080  # ← Port 8080!

  inference:
    image: nginx:1.28.0
    ports:
      - "${PORT:-8080}:8080"           # PoC/Management API
      - "${INFERENCE_PORT:-5050}:5000" # Inference requests
```

### Official MLNode Setup Script

From `mlnode.sh`:
```bash
export PORT=8080              # ML Node Port
export INFERENCE_PORT=5050    # Inference Port
```

### Official Registration Script

From `register-disable-mlnode.sh`, the registration payload includes:
```json
{
  "id": "node-name",
  "host": "GPU_SERVER_IP",
  "inference_port": 5050,
  "poc_port": 8080,        # ← Port 8080 for PoC!
  "models": [...]
}
```

## The Fix

### 1. Updated Environment Variable

**File: `config/.env.example`**

```bash
# WRONG (before):
# MLNODE_PORT=5070

# CORRECT (after):
MLNODE_PORT=8080  # Official MLNode runs on port 8080
```

### 2. Updated Python Code

**File: `scripts/mlnode_poc_manager.py`**

```python
# Line 38 - Changed default port from 5070 to 8080
self.mlnode_port = int(os.getenv('MLNODE_PORT', '8080'))  # Official MLNode runs on 8080
```

Updated port detection:
- Search for `$VAST_TCP_PORT_8080` (was `$VAST_TCP_PORT_5070`)
- Parse `extra_env` for `(\d+):8080` pattern (was `:5070`)

### 3. Updated Vast.ai Port Mapping

**File: `scripts/2_vastai_manager.py`**

```python
data = {
    'client_id': 'me',
    'image': resolved_image,
    'disk': disk,
    'label': 'gonka-poc-sprint',
    'env': {'-p 8080:8080': ''}  # Expose MLNode API port 8080
}
```

## Port Summary

The official MLNode setup uses TWO ports:

| Port | Purpose | Exposed By |
|------|---------|------------|
| **8080** | PoC Operations & Management API | `mlnode-308` service |
| **5050** | Inference Requests | `inference` (nginx) service |

For our Vast.ai just-in-time GPU setup, we only need to expose **port 8080** since:
- The Network Node (running on VPS) manages PoC operations via port 8080
- We're not running the nginx inference proxy on Vast.ai
- We connect directly to the MLNode API

## Architecture

```
┌─────────────────────────┐
│   VPS (CPU Server)      │
│  ┌──────────────────┐   │
│  │ Network Node     │   │ :8000
│  │ TMKMS            │   │
│  │ Admin API        │   │ :9200
│  └──────────────────┘   │
└─────────────────────────┘
         ↕ HTTP
    Register MLNode
    POST /admin/v1/nodes
    {
      "poc_port": 8080,
      "inference_port": 5050
    }
         ↕
┌─────────────────────────┐
│ Vast.ai (GPU Server)    │
│  ┌──────────────────┐   │
│  │ MLNode Container │   │
│  │ Port 8080        │   │ ← PoC API
│  │ (uvicorn)        │   │
│  └──────────────────┘   │
└─────────────────────────┘
```

## Testing

After this fix, you should see:

**In Vast.ai logs:**
```
docker create ... -p [EXTERNAL_PORT]:8080 ... --name C.XXXXXXX
```

**In VPS logs:**
```
DEBUG - Found port mapping in extra_env: [EXTERNAL_PORT]:8080
MLNode URL: http://ssh7.vast.ai:[EXTERNAL_PORT]
```

**Environment variable check:**
```bash
# Inside the Vast.ai container
echo $VAST_TCP_PORT_8080
# Should output: [EXTERNAL_PORT]
```

## References

- [Official Gonka MLNode Setup](https://github.com/ezlabsnodes/gonka/blob/main/mlnode.sh)
- [MLNode Docker Compose](https://github.com/gonka-ai/gonka/blob/312044d28c7170d7f08bf88e41427396f3b95817/deploy/join/docker-compose.mlnode.yml)
- [MLNode Registration Script](https://github.com/ezlabsnodes/gonka/blob/main/register-disable-mlnode.sh)
- [Gonka Multiple Nodes Guide](https://gonka.ai/host/multiple-nodes/)

## Next Steps

1. Update your local `.env` file with `MLNODE_PORT=8080`
2. Test with: `python3 test_mlnode_poc_integration.py --skip-poc`
3. Verify port 8080 is exposed in Vast.ai logs
4. Confirm MLNode API responds at `http://[host]:[port]/api/v1/state`

---

**Status:** Ready to test with correct port configuration! 🎉
