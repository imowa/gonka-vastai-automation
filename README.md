# Gonka Hybrid MLNode - Automated Setup

> 💰 Run a Gonka MLNode for low monthly cost by combining Hyperbolic API
> inference with on-demand Vast.ai GPUs for PoC.

## What This Repository Does

This project automates a **hybrid Gonka MLNode** that:
- 🤖 Uses **Hyperbolic API** for 24/7 inference (no local GPU needed)
- 🚀 Automatically rents **Vast.ai GPUs** only for PoC sprints
- 📉 Reduces GPU spend by renting only during PoC

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    GONKA NETWORK                            │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              YOUR VPS (4 vCPU, 16GB RAM)                    │
│                                                              │
│  ┌──────────────────────┐  ┌───────────────────────────┐   │
│  │  Hyperbolic Proxy    │  │   PoC Scheduler           │   │
│  │  (24/7 Inference)    │  │   (Auto GPU Rental)       │   │
│  │                      │  │                            │   │
│  │  • Always online     │  │  • Detects PoC early       │   │
│  │  • No GPU needed     │  │  • Rents Vast.ai GPU       │   │
│  │  • Hyperbolic API    │  │  • Runs PoC sprint         │   │
│  └──────────────────────┘  │  • Stops GPU after         │   │
│                             │                            │   │
│                             └───────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## PoC Workflow (Official Reference)

The Gonka PoC (Proof-of-Compute) flow is implemented in the MLNode PoW package
and is coordinated via MLNode REST endpoints. The network node only receives
results; it does not run PoC compute or validation.

### 1) MLNode runs PoC compute + validation

Implementation references in the official MLNode repo:
- PoC compute engine: `mlnode/packages/pow/src/pow/compute/`
- PoC validation: `mlnode/packages/pow/src/pow/compute/compute.py`
- PoC service orchestration: `mlnode/packages/pow/src/pow/service/manager.py`

### 2) MLNode exposes PoC REST endpoints

Canonical endpoints (OpenAPI):
- `/api/v1/pow/init`
- `/api/v1/pow/init/generate`
- `/api/v1/pow/init/validate`
- `/api/v1/pow/phase/generate`
- `/api/v1/pow/phase/validate`
- `/api/v1/pow/validate`
- `/api/v1/pow/status`
- `/api/v1/pow/stop`

Authoritative OpenAPI spec source in the MLNode repo:
- `mlnode/packages/api/docs/openapi.json`

### 3) Init-generate payload (what PoC expects)

From `mlnode/packages/pow/tests/init_generate.sh` and the OpenAPI schema:
- `node_id`, `node_count`
- `block_hash`, `block_height`
- `public_key`
- `batch_size`, `r_target`, `fraud_threshold`
- `params` (model-specific)
- `url` (callback receiver URL)

### 4) Validation payload (ProofBatch)

The `/api/v1/pow/validate` endpoint expects:
- `public_key`
- `block_hash`, `block_height`
- `nonces` (array)
- `dist` (array)

### 5) Callback flow back to the network node

MLNode pushes PoC batch results to the network node at:
- `/v1/poc-batches` (base callback)

The PoC server appends `/generated` or `/validated` to this base URL depending
on phase.

Callback payloads sent by MLNode:
- `generated` callback uses `ProofBatch`:
  - `public_key`
  - `block_hash`, `block_height`
  - `nonces` (array of int64)
  - `dist` (array of float64)
  - `node_id` (uint64)
- `validated` callback uses `ValidatedBatch`:
  - `ProofBatch` fields (above)
  - `received_dist` (array of float64)
  - `r_target` (float64)
  - `fraud_threshold` (float64)
  - `n_invalid` (int64)
  - `probability_honest` (float64)
  - `fraud_detected` (bool)

### 6) Auth, timeouts, retries, and errors

Auth:
- PoC endpoints (`/api/v1/pow/*`) are called without auth headers.
- Callbacks (`/v1/poc-batches/(generated|validated)`) do not check auth headers
  or signatures; they bind JSON and process it.

Timeouts and retries:
- PoC HTTP client timeout is 15 minutes.
- No retry/backoff is performed in the PoC request path.

Callback error handling:
- Invalid JSON returns `400 Bad Request`.
- Chain submission errors surface as server errors.

## Prerequisites

### 1) VPS
- 4+ vCPU
- 16GB+ RAM
- Ubuntu 22.04+

### 2) API Keys
- Hyperbolic API key (inference)
- Vast.ai API key (PoC GPU rentals)

### 3) Gonka Network Node
You should have the Gonka Network Node running and accessible
via the admin API (default: `http://localhost:9200`).

## Quick Start

### Step 1: Clone and create a virtualenv

```bash
git clone https://github.com/YOUR_USERNAME/gonka-vastai-automation
cd gonka-vastai-automation
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Step 2: Configure environment

Create `config/.env` (use `config/.env.example` as a template) and
set your keys. Example:

```bash
# Hyperbolic API (inference)
HYPERBOLIC_API_KEY=your_hyperbolic_api_key_here
HYPERBOLIC_MODEL=Qwen/QwQ-32B
HYPERBOLIC_BASE_URL=https://api.hyperbolic.xyz/v1
HYPERBOLIC_PROXY_PORT=8080

# Vast.ai (PoC rentals)
VASTAI_API_KEY=your_vastai_api_key_here
VASTAI_SSH_KEY_PATH=~/.ssh/id_rsa
VASTAI_GPU_TYPE=ANY
VASTAI_MIN_VRAM=40
VASTAI_MAX_PRICE=0.60
VASTAI_DISK_SIZE=50

# Gonka admin API
GONKA_ADMIN_API_URL=http://localhost:9200
```

### Step 3: Start Hyperbolic inference proxy

This runs on your VPS (no GPU required) and registers itself with the Gonka
admin API. It automatically loads `config/.env` if present.

```bash
source venv/bin/activate
python3 scripts/hyperbolic_proxy.py
```

Default settings (override via environment variables):
- `MLNODE_ID` or `NODE_ID` (default: `hyperbolic-proxy-1`)
- `VPS_IP` (default: `198.74.55.121`)
- `HYPERBOLIC_PROXY_PORT` or `PROXY_PORT` (default: `8080`)
- `HYPERBOLIC_API_KEY` (required)
- `HYPERBOLIC_MODEL`, `MLNODE_MODEL`, or `MODEL_NAME` (default: `Qwen/QwQ-32B`)
- `HYPERBOLIC_BASE_URL` (default: `https://api.hyperbolic.xyz`, accepts `/v1`)
- `GONKA_ADMIN_API_URL` (default: `http://localhost:9200`)
- `INFERENCE_SEGMENT` (default: `/v1`)
- `POC_SEGMENT` (default: `/api/v1`)
- `HARDWARE_TYPE` (default: `Hyperbolic-API`)
- `HARDWARE_COUNT` (default: `1`)

The proxy also accepts version-prefixed paths (for example: `/v3.0.8/api/v1/*`
or `/v3.0.8/v1/chat/completions`) to align with the network node URL builder.

### Step 4: Start PoC scheduler (Vast.ai)

```bash
source venv/bin/activate
python3 scripts/3_poc_scheduler.py
```

The scheduler monitors the chain and spins up Vast.ai GPUs for PoC windows.

### Step 5: Run a live PoC test (manual)

Use the live test script to validate GPU rental, vLLM startup, and PoC flow.

```bash
source venv/bin/activate
python3 test_live_poc.py --yes --estimated-minutes 15
```

Optional flags:
- `--docker-image vllm/vllm-openai:latest` to override the Vast.ai image
- `--wait-timeout 1800` to extend the vLLM startup timeout (seconds)
- `--skip-poc` to validate provisioning without running the PoC sprint

## Key Scripts

- `scripts/hyperbolic_proxy.py`: Hyperbolic inference proxy + MLNode endpoints
- `scripts/3_poc_scheduler.py`: PoC scheduler (GPU rentals + vLLM)
- `scripts/1_poc_monitor.py`: PoC timing monitor
- `scripts/2_vastai_manager.py`: Vast.ai API manager
- `scripts/5_vllm_proxy_manager.py`: Remote vLLM manager

## FAQ

**Can I run the MLNode inference without a GPU?**  
Yes. The Hyperbolic proxy runs on a CPU-only VPS and forwards inference to the
Hyperbolic API. GPUs are only required for PoC runs via Vast.ai.

**Do I still need Vast.ai?**  
Yes, for PoC sprints. Inference can be fully offloaded to Hyperbolic.

## License

MIT
