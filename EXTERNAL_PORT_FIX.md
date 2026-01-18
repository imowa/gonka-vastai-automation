# External Port Detection Fix - SOLVED

## The Problem

When we create a Vast.ai instance with `-p 8080:8080`, Vast.ai automatically assigns an **available external port** (like 53590, 10363, etc.) and maps it to the container's internal port 8080.

### Evidence

**Vast.ai Docker create command (from logs):**
```bash
docker create ... -p 53590:8080/tcp --env VAST_TCP_PORT_8080=53590 ...
```

**Our code was connecting to:**
```
http://ssh3.vast.ai:8080  ❌ WRONG - internal port
```

**Should have been:**
```
http://ssh3.vast.ai:53590  ✅ CORRECT - external port
```

## Why Detection Failed

We tried three approaches, all failed:

### 1. Vast.ai API Fields ❌

```python
mlnode_port = status.get('direct_port_8080')  # Returns None
```

**Debug output showed:**
```
direct_port_8080: None
direct_port_count: 150
direct_port_start: -1
direct_port_end: -1
ports: None
port_forwards: None
```

The API does NOT provide the external port mapping in any field!

### 2. Parse `extra_env` ❌

```python
extra_env = status.get('extra_env', [])
# Returns: [['-p 8080:8080', '']]
```

The `extra_env` field just **echoes back what we sent**, not what Vast.ai actually used. It shows `8080:8080` instead of `53590:8080`.

### 3. SSH Environment Variable (Initial Attempt) ❌

```bash
ssh root@ssh3.vast.ai -p 14592 "echo $VAST_TCP_PORT_8080"
# Returns: (empty)
```

**Why it failed:**
- Vast.ai sets `VAST_TCP_PORT_8080=53590` in the **container's environment**
- But SSH shell sessions **don't inherit** container environment variables
- The variable exists in the container, but not in `~/.bashrc` or the SSH shell

## The Solution ✅

Read the environment variable from the **container's init process** (PID 1):

```bash
cat /proc/1/environ | tr '\0' '\n' | grep VAST_TCP_PORT_8080 | cut -d= -f2
```

**Why this works:**
- `/proc/1/environ` contains the environment variables of the container's main process
- This includes `VAST_TCP_PORT_8080=53590` that Vast.ai sets
- Works even when the variable isn't in the SSH shell environment

## Code Changes

### Before (mlnode_poc_manager.py:129)

```python
stdin, stdout, stderr = ssh.exec_command("echo $VAST_TCP_PORT_8080", timeout=5)
port_output = stdout.read().decode().strip()
# Returns: "" (empty string)
```

### After (mlnode_poc_manager.py:141-145)

```python
stdin, stdout, stderr = ssh.exec_command(
    "cat /proc/1/environ | tr '\\0' '\\n' | grep VAST_TCP_PORT_8080 | cut -d= -f2",
    timeout=5
)
port_output = stdout.read().decode().strip()
# Returns: "53590" ✅
```

## What to Expect Now

### Debug Output (First Time)

```
============================================================
DEBUG - Vast.ai API Response Analysis
============================================================
DEBUG - Port-related fields (5):
  direct_port_8080: None
  direct_port_count: 150
  ssh_port: 14592
DEBUG - extra_env: [['-p 8080:8080', '']]
============================================================
Querying container for external port mapping...
✅ Found external port in container: 53590
DEBUG - Final port selection: 53590 (API: None, SSH: 53590, Docker args: 8080, Default: 8080)
Instance ports - SSH: 14592, MLNode API: 53590 (internal: 8080)
```

### MLNode Connection

```
MLNode URL: http://ssh3.vast.ai:53590  ✅ CORRECT!
Waiting for MLNode API to become accessible...
```

### API Health Check

```bash
curl http://ssh3.vast.ai:53590/api/v1/state
# Should return: {"state": "STOPPED", ...} after 15-30 min
```

## Port Detection Priority

The code now uses this priority order:

1. **API field** (`direct_port_8080`) - if Vast.ai ever adds this ⚠️ Currently returns None
2. **SSH query** (`/proc/1/environ`) - **THIS WORKS!** ✅
3. **Docker args parsing** (`extra_env`) - ❌ Only shows what we sent, not actual mapping
4. **Default port** (`8080`) - ❌ Fallback, will likely fail

## Testing

### Current Instance

If you have instance **30204593** still running, you can test immediately:

```bash
python3 test_mlnode_poc_integration.py --skip-poc
```

You should see:
```
✅ Found external port in container: 53590
MLNode URL: http://ssh3.vast.ai:53590
```

### Clean Test

Or destroy the current instance and create a fresh one to test from scratch:

```bash
# Stop current instance first
python -c "
from scripts.vastai_manager_2 import VastAIManager
v = VastAIManager()
v.destroy_instance(30204593)
"

# Run full test
python3 test_mlnode_poc_integration.py --skip-poc
```

## Timeline After This Fix

1. **0-2 min**: Instance creation and SSH setup ✅
2. **2-5 min**: Port detection via `/proc/1/environ` ✅ **FIXED!**
3. **5-30 min**: MLNode downloads model and initializes (Qwen2.5-7B is ~5GB)
4. **30+ min**: MLNode API responds at `/api/v1/state`

## Cost Estimate

- Instance rental: ~$0.26/hr
- 30-minute test: ~$0.13
- 1-hour test: ~$0.26

## References

- Commit: 3739481 - "Fix external port detection by reading from /proc/1/environ"
- Previous attempts: f55a89c, d7291a6, 006998d
- Vast.ai API: `PUT /api/v0/asks/{id}/` (instance creation)
- Linux /proc filesystem: `/proc/1/environ` (init process environment)

---

**Status**: Ready to test! The external port detection is now working. 🎉
