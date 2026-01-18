# MLNode Port Exposure Fix ✅

## Problem Discovered

Your MLNode container was running successfully on Vast.ai, but the **MLNode API port (5070) was NOT accessible from outside** the container.

### Evidence from Your Logs

```
2026-01-16 16:32:23 - MLNode URL: http://ssh2.vast.ai:5070
2026-01-16 16:32:23 - Waiting for MLNode API to become accessible...
```

Then the connection kept failing because port 5070 wasn't exposed to the internet.

Looking at the Docker create command in your Vast.ai logs:
```
docker create ... --env PUBLIC_IPADDR=74.15.83.102 ... --name C.30112153
```

**No `-p 5070:5070` port mapping!** Only SSH port was mapped.

## Root Cause

When you create a Vast.ai instance, you need to explicitly tell it which ports to expose. The MLNode Docker image internally runs on port 5070, but without port mapping, that port stays **inside the container only**.

## The Fix

### 1. Expose Port When Creating Instance

**File: `scripts/2_vastai_manager.py`**

Added port mapping to the create instance request:

```python
data = {
    'client_id': 'me',
    'image': resolved_image,
    'disk': disk,
    'label': 'gonka-poc-sprint',
    'env': "-p 5070:5070/tcp"  # ✅ Expose MLNode API port (must be STRING)
}
```

**Important:** The `env` field must be a STRING containing Docker run options (like `-p`, `-e`, `-h` flags), NOT a dictionary or array.

### 2. Read Externally Mapped Port

**File: `scripts/mlnode_poc_manager.py`**

Vast.ai might map port 5070 to a different external port (e.g., 5070 → 45123). We need to read this mapping:

```python
# Get the externally mapped MLNode port (Vast.ai maps internal ports to external ones)
mlnode_port = status.get(f'direct_port_{self.mlnode_port}') or \
             status.get('direct_port_5070') or \
             self.mlnode_port  # Fallback to default
```

### 3. Use Correct Port in MLNode URL

```python
mlnode_host = ssh_info['host']
mlnode_port = ssh_info.get('mlnode_port', self.mlnode_port)  # Use mapped port
mlnode_url = f"http://{mlnode_host}:{mlnode_port}"
```

## How Port Mapping Works on Vast.ai

### Before Fix:
```
Internet → Vast.ai Host → Container
          ↓
          Only SSH port 32152 exposed
          Port 5070 NOT accessible ❌
```

### After Fix:
```
Internet → Vast.ai Host → Container
          ↓
          SSH port: 32152 → 22
          MLNode API: [mapped_port] → 5070 ✅
```

## What to Expect Now

When you create a new instance:

1. ✅ Vast.ai will expose port 5070 to the internet
2. ✅ Your code will read the mapped port number
3. ✅ MLNode API will be accessible at `http://ssh2.vast.ai:[mapped_port]`
4. ✅ The startup process will complete successfully

### Example Expected Logs:

```
2026-01-16 XX:XX:XX - Instance ports - SSH: 32152, MLNode API: 45123 (internal: 5070)
2026-01-16 XX:XX:XX - MLNode URL: http://ssh2.vast.ai:45123
2026-01-16 XX:XX:XX - Waiting for MLNode API to become accessible...
[15-30 min later]
2026-01-16 XX:XX:XX - ✅ MLNode is ready (state: STOPPED)
```

## Testing the Fix

### Clean Up Current Instance First

The instance you created earlier (30112153) doesn't have port 5070 exposed, so you need to stop it:

```bash
# From your VPS
python -c "
from scripts.vastai_manager_2 import VastAIManager
v = VastAIManager()
v.destroy_instance(30112153)  # Or whatever instance ID you have
"
```

Or just destroy it via Vast.ai web console.

### Test the New Fix

```bash
python test_mlnode_poc_integration.py --skip-poc
```

**Expected timeline:**
- 0-2 min: Instance provisioning
- 2-5 min: Docker image setup and SSH configuration (from your logs this completes)
- 5-30 min: MLNode downloads model and initializes
- Total: ~20-35 minutes

**Cost:** ~$0.15-0.25 for 30-45 min test

## Important Notes

### Port Availability

Vast.ai providers control which ports are available. Some providers block certain ports. If port 5070 is blocked:

- Vast.ai will automatically map it to an available port
- Your code now reads this mapped port automatically
- Everything will still work ✅

### Firewall Rules

The MLNode Docker image should already have proper firewall rules since it's designed to expose the API. This fix just ensures Vast.ai actually exposes it.

## Troubleshooting

### If Still Not Connecting:

1. **Check instance status in Vast.ai console**
   - Is the container running?
   - Are there any errors in the logs?

2. **Verify port is exposed**
   ```bash
   # Check instance details
   curl -X GET "https://console.vast.ai/api/v0/instances/INSTANCE_ID/?api_key=YOUR_KEY"
   ```
   Look for `direct_port_5070` in the response.

3. **Test port manually**
   ```bash
   # From your local machine
   curl http://ssh2.vast.ai:PORT/api/v1/state
   ```
   Replace PORT with the mapped port from logs.

## Next Steps After This Works

Once the port exposure is working, you might still encounter the model download time issue. Consider:

1. **Use persistent storage** - Keep models cached between instances (costs more but faster)
2. **Build custom image** - Pre-bake the model into the Docker image (advanced)
3. **Increase timeout** - If 30 min isn't enough, increase `MLNODE_STARTUP_TIMEOUT`

---

**Status:** Ready to test! Destroy the old instance and create a new one to test the fix.
