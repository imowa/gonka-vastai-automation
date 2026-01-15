# Migration Guide: Official MLNode Integration

This guide explains the changes made to integrate with the official MLNode PoC implementation.

## What Changed?

### Before (Raw vLLM)
Your automation was starting **raw vLLM** directly on Vast.ai GPUs. This had limitations:
- ❌ No official PoC endpoints (`/api/v1/pow/*`)
- ❌ No PoC compute engine
- ❌ No PoC validation logic
- ❌ No automatic callbacks to Network Node
- ⚠️ Only had OpenAI-compatible inference endpoints

### After (Official MLNode)
Now uses the **official MLNode Docker container** which includes:
- ✅ Complete PoC implementation (`mlnode/packages/pow`)
- ✅ All PoC API endpoints (`/api/v1/pow/*`)
- ✅ PoC compute engine (`compute.py`)
- ✅ PoC validation (`validate.py`)
- ✅ Automatic callbacks (`sender.py`)
- ✅ Full compatibility with Gonka network protocol

## Architecture Changes

### Inference Layer (No Changes Required)
The **Hyperbolic Proxy** (`scripts/hyperbolic_proxy.py`) continues to:
- Handle all inference requests 24/7
- Route to Hyperbolic API (no GPU needed)
- Register as inference-only node

**Changes:**
- Removed stub PoC endpoints (they were non-functional)
- Clarified that it's inference-only

### PoC Layer (New Integration)
**New:** `scripts/mlnode_poc_manager.py`
- Manages official MLNode Docker containers on Vast.ai GPUs
- Waits for MLNode to fully initialize
- Registers MLNode with Network Node
- Monitors PoC completion via admin API

**Updated:** `scripts/3_poc_scheduler.py`
- Now uses `MLNodePoCManager` instead of `RemoteVLLMManager`
- Deploys official MLNode container instead of starting vLLM manually
- Network Node automatically calls MLNode PoC endpoints
- MLNode handles all PoC computation and callbacks

## New Configuration Variables

Add these to your `config/.env`:

```bash
# Official MLNode Configuration (PoC)
MLNODE_PORT=5070
MLNODE_API_SEGMENT=/api/v1
MLNODE_INFERENCE_SEGMENT=/v1
MLNODE_STARTUP_TIMEOUT=1800
POC_EXECUTION_TIMEOUT=900
```

## Testing Your Setup

### 1. Test Manager Only (Free)
```bash
python3 test_mlnode_poc_integration.py --manager-only
```

This verifies:
- SSH key is configured
- Network Node API is accessible
- MLNode manager is initialized

### 2. Full Integration Test (Rents GPU)
```bash
python3 test_mlnode_poc_integration.py --yes --estimated-minutes 15
```

This will:
1. Rent a Vast.ai GPU
2. Deploy official MLNode container
3. Wait for initialization (~15-20 minutes for model download)
4. Register with Network Node
5. Monitor PoC execution
6. Clean up automatically

## PoC Flow Diagram

```
┌──────────────────────────────────────────────────────────────┐
│  1. Scheduler detects PoC timing                              │
│     (scripts/1_poc_monitor.py monitors blockchain)            │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────┐
│  2. Rent Vast.ai GPU 30 minutes before PoC                    │
│     (scripts/3_poc_scheduler.py)                              │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────┐
│  3. Deploy official MLNode container                          │
│     (scripts/mlnode_poc_manager.py)                           │
│     • SSH to GPU instance                                     │
│     • Wait for container startup                              │
│     • Wait for model loading                                  │
│     • Check MLNode health endpoint                            │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────┐
│  4. Register MLNode with Network Node                         │
│     POST /admin/v1/nodes                                      │
│     {                                                          │
│       "id": "vastai-mlnode-12345",                            │
│       "host": "gpu_host",                                     │
│       "poc_port": 5070,                                       │
│       "poc_segment": "/api/v1",                               │
│       ...                                                      │
│     }                                                          │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────┐
│  5. Network Node automatically triggers PoC                   │
│     POST http://gpu_host:5070/api/v1/pow/init/generate       │
│     POST http://gpu_host:5070/api/v1/pow/phase/generate      │
│     POST http://gpu_host:5070/api/v1/pow/phase/validate      │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────┐
│  6. MLNode runs PoC compute and validation                    │
│     (Official implementation in mlnode/packages/pow)          │
│     • Generate proofs (compute.py)                            │
│     • Validate proofs (validate.py)                           │
│     • Send callbacks to Network Node (sender.py)              │
│       - POST /v1/poc-batches/generated                        │
│       - POST /v1/poc-batches/validated                        │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────┐
│  7. Cleanup                                                    │
│     • Unregister MLNode from Network Node                     │
│     • Stop and destroy GPU instance                           │
│     • Re-register Hyperbolic Proxy for inference              │
└──────────────────────────────────────────────────────────────┘
```

## File Changes Summary

### New Files
- `scripts/mlnode_poc_manager.py` - Official MLNode container manager
- `test_mlnode_poc_integration.py` - Integration test script
- `MIGRATION.md` - This file

### Modified Files
- `scripts/3_poc_scheduler.py` - Uses MLNodePoCManager instead of RemoteVLLMManager
- `scripts/hyperbolic_proxy.py` - Removed stub PoC endpoints, clarified inference-only
- `README.md` - Added official MLNode integration documentation

### Unchanged Files
- `scripts/1_poc_monitor.py` - PoC timing monitor
- `scripts/2_vastai_manager.py` - Vast.ai API manager
- `scripts/5_vllm_proxy_manager.py` - Kept for backward compatibility

## Troubleshooting

### MLNode Container Won't Start
1. Check Docker image is correct in `config/.env`:
   ```bash
   DOCKER_IMAGE=ghcr.io/product-science/mlnode:3.0.11-post1@sha256:0cf224b2f88694def989731ecdd23950a6d899be5d70e01e8dcf823b906199af
   ```
2. Check SSH access to GPU instance
3. Check GPU has enough VRAM (minimum 24GB)
4. Review container logs via SSH:
   ```bash
   ssh -p <port> root@<host>
   docker logs $(docker ps -q)
   ```

### MLNode Initialization Timeout
The official MLNode needs to:
1. Start container (~2-3 minutes)
2. Download model (~10-15 minutes)
3. Load model into GPU (~2-5 minutes)

If timeout occurs:
- Increase `MLNODE_STARTUP_TIMEOUT` in `config/.env`
- Use smaller model for PoC: `MLNODE_POC_MODEL=Qwen/Qwen2.5-7B-Instruct`

### PoC Not Completing
1. Check Network Node is calling MLNode PoC endpoints:
   ```bash
   # On GPU via SSH
   docker logs $(docker ps -q) | grep "/api/v1/pow"
   ```
2. Verify MLNode is registered:
   ```bash
   curl http://localhost:9200/admin/v1/nodes | jq
   ```
3. Check MLNode state:
   ```bash
   curl http://<gpu_host>:5070/api/v1/state
   ```

## Rollback (If Needed)

If you need to revert to the previous vLLM-based implementation:

1. Restore `scripts/3_poc_scheduler.py` from git:
   ```bash
   git checkout HEAD~1 scripts/3_poc_scheduler.py
   ```

2. The old flow will use `RemoteVLLMManager` from `scripts/5_vllm_proxy_manager.py`

**Note:** The old implementation won't work for PoC because it lacks the official PoC endpoints.

## Support

For issues:
1. Run the integration test with verbose logging
2. Check GPU instance logs via SSH
3. Verify Network Node can reach the MLNode endpoints
4. Open an issue in the repository with logs

## Next Steps

1. Update your `config/.env` with new MLNode variables
2. Run `python3 test_mlnode_poc_integration.py --manager-only`
3. If test passes, run full integration test
4. Start the scheduler and let it handle PoC automatically

You now have full official MLNode integration! 🎉
