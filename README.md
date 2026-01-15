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

## Official MLNode Integration

This automation now uses the **official MLNode Docker container** for PoC operations, ensuring full compatibility with the Gonka network protocol.

### How It Works

1. **Inference (24/7)**: Hyperbolic Proxy handles all inference requests
   - Runs on your VPS (no GPU needed)
   - Routes requests to Hyperbolic API
   - Registered with Network Node as inference-only node

2. **PoC (On-Demand)**: Official MLNode Container on Vast.ai GPU
   - Scheduler detects PoC timing from blockchain
   - Automatically rents Vast.ai GPU ~30 minutes before PoC
   - Deploys official MLNode Docker container (`ghcr.io/product-science/mlnode`)
   - MLNode handles all PoC compute and validation using official implementation
   - Automatically unregisters and stops GPU after PoC completes

### Key Components

- **`scripts/hyperbolic_proxy.py`**: Inference-only proxy (Hyperbolic API)
- **`scripts/mlnode_poc_manager.py`**: Official MLNode container manager
- **`scripts/3_poc_scheduler.py`**: Automated PoC orchestration
- **`scripts/1_poc_monitor.py`**: Blockchain monitoring for PoC timing

### Official MLNode PoC Flow

```
┌─────────────────────────────────────────────────────────────┐
│  Network Node detects PoC phase                              │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  Network Node calls MLNode PoC endpoints                     │
│  • /api/v1/pow/init/generate                                 │
│  • /api/v1/pow/phase/generate                                │
│  • /api/v1/pow/phase/validate                                │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  Official MLNode Container (Vast.ai GPU)                     │
│  • Runs PoC compute (mlnode/packages/pow/compute)            │
│  • Validates proofs (mlnode/packages/pow/validate)           │
│  • Sends callbacks to Network Node                           │
│    - /v1/poc-batches/generated                               │
│    - /v1/poc-batches/validated                               │
└─────────────────────────────────────────────────────────────┘
```

The official MLNode implementation includes:
- Full PoC compute engine (`mlnode/packages/pow/src/pow/compute/compute.py`)
- PoC service orchestration (`mlnode/packages/pow/src/pow/service/manager.py`)
- Automatic callbacks to Network Node (`mlnode/packages/pow/src/pow/service/sender.py`)

This ensures 100% compatibility with the Gonka network protocol.

## Dual Model Strategy

This system uses an optimized dual-model approach:

### PoC Sprint (Vast.ai GPU Rental)
- **Model:** Qwen/Qwen2.5-7B-Instruct (small, efficient)
- **Purpose:** Proof of Compute validation
- **Hardware:** 1x RTX 4090 (24GB)
- **Cost:** ~$0.23/hr (~$1-2/month for PoC sprints)
- **Why small model:** PoC doesn't require the smartest model, just compute proof

### Regular Inference (Hyperbolic API)
- **Model:** Qwen/QwQ-32B (large, smart)
- **Purpose:** Serving inference requests 24/7
- **Hardware:** Managed by Hyperbolic (infinite scale)
- **Cost:** ~$20-40/month based on usage
- **Why large model:** Inference quality matters for user experience

### Total Monthly Cost
- **PoC GPU rental:** ~$1-2/month
- **Inference API:** ~$20-40/month
- **Total:** ~$21-42/month

### Cost Comparison
| Strategy | PoC | Inference | Total/mo |
|----------|-----|-----------|----------|
| 24/7 GPU (2x 4090) | $340 | - | ~$340 |
| 24/7 GPU (1x 4090) | $170 | - | ~$170 |
| **Our hybrid approach** | **$1-2** | **$20-40** | **~$21-42** ✅ |

**Savings: ~88-94% compared to 24/7 GPU rental!**

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

## Inference Routing (Transfer vs Executor)

The Hyperbolic proxy can optionally forward initial inference requests to a
Gonka executor when it detects a transfer request (missing `X-Inference-Id`
and `X-Seed`). When enabled, the proxy:

- Computes `X-Prompt-Hash` from the raw request body.
- Adds `X-Inference-Id`, `X-Seed`, and `X-Timestamp`.
- Forwards the request to `EXECUTOR_BASE_URL` + `EXECUTOR_INFERENCE_PATH`.

If `X-Inference-Id` and `X-Seed` are already present (executor request), the
proxy routes the request to Hyperbolic and injects the seed into the request
body. This keeps executor semantics while still using the Hyperbolic API for
model execution.

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

# Transfer routing (forward initial requests to a Gonka executor)
ENABLE_TRANSFER_ROUTING=true
EXECUTOR_BASE_URL=https://executor.example.com
EXECUTOR_INFERENCE_PATH=/v1/chat/completions
INFERENCE_FORWARD_TIMEOUT=300
TRANSFER_ADDRESS=gonka1transferaddresshere
REQUESTER_ADDRESS=gonka1requesteraddresshere
REQUIRE_TRANSFER_SIGNATURE=false

# Dual model config
MLNODE_POC_MODEL=Qwen/Qwen2.5-7B-Instruct
MLNODE_INFERENCE_MODEL=Qwen/QwQ-32B
MLNODE_MODEL=${MLNODE_POC_MODEL}

# Vast.ai (PoC rentals)
VASTAI_API_KEY=your_vastai_api_key_here
VASTAI_SSH_KEY_PATH=~/.ssh/id_rsa
VASTAI_GPU_TYPE=ANY
VASTAI_NUM_GPUS=1
VASTAI_MIN_VRAM=24
VASTAI_MAX_PRICE=0.30
VASTAI_DISK_SIZE=50
DOCKER_IMAGE=ghcr.io/product-science/mlnode:3.0.11-post1@sha256:0cf224b2f88694def989731ecdd23950a6d899be5d70e01e8dcf823b906199af

# Official MLNode Configuration (PoC)
MLNODE_PORT=5070
MLNODE_API_SEGMENT=/api/v1
MLNODE_INFERENCE_SEGMENT=/v1
MLNODE_STARTUP_TIMEOUT=1800
POC_EXECUTION_TIMEOUT=900

# Gonka admin API
GONKA_ADMIN_API_URL=http://localhost:9200
```

> ✅ **Official MLNode Integration**: The automation now uses the official MLNode
> Docker container which includes the complete PoC implementation (compute engine,
> validation, and callbacks). The container is deployed on Vast.ai GPUs only during
> PoC windows, and the Network Node communicates directly with the MLNode API.

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
- `MLNODE_INFERENCE_MODEL`, `HYPERBOLIC_MODEL`, or `MODEL_NAME` (default: `Qwen/QwQ-32B`)
- `HYPERBOLIC_BASE_URL` (default: `https://api.hyperbolic.xyz`, accepts `/v1`)
- `GONKA_ADMIN_API_URL` (default: `http://localhost:9200`)
- `INFERENCE_SEGMENT` (default: `/v1`)
- `POC_SEGMENT` (default: `/api/v1`)
- `HARDWARE_TYPE` (default: `Hyperbolic-API`)
- `HARDWARE_COUNT` (default: `1`)
- `ENABLE_TRANSFER_ROUTING` (default: `true`)
- `EXECUTOR_BASE_URL` (default: empty, required for transfer forwarding)
- `EXECUTOR_INFERENCE_PATH` (default: `/v1/chat/completions`)
- `INFERENCE_FORWARD_TIMEOUT` (default: `300`)
- `TRANSFER_ADDRESS` (default: empty)
- `REQUESTER_ADDRESS` (default: empty)
- `REQUIRE_TRANSFER_SIGNATURE` (default: `false`)

The proxy also accepts version-prefixed paths (for example: `/v3.0.8/api/v1/*`
or `/v3.0.8/v1/chat/completions`) to align with the network node URL builder.

### Step 4: Start PoC scheduler (Vast.ai)

```bash
source venv/bin/activate
python3 scripts/3_poc_scheduler.py
```

The scheduler monitors the chain and spins up Vast.ai GPUs for PoC windows.

### Step 5: Test official MLNode integration

Use the integration test script to validate the complete PoC flow with the official MLNode container.

```bash
source venv/bin/activate

# Test MLNode manager only (no GPU rental)
python3 test_mlnode_poc_integration.py --manager-only

# Full integration test (rents GPU and runs PoC)
python3 test_mlnode_poc_integration.py --yes --estimated-minutes 15
```

Optional flags:
- `--manager-only`: Test manager initialization without GPU rental
- `--skip-poc`: Test provisioning without waiting for PoC execution
- `--yes`: Skip confirmation prompt
- `--estimated-minutes N`: Set expected test duration (default: 15)

The test will:
1. Rent a Vast.ai GPU
2. Deploy the official MLNode Docker container
3. Wait for MLNode to initialize (model download ~15-20 minutes)
4. Register MLNode with the Network Node
5. Monitor PoC execution (if not skipped)
6. Clean up and stop the GPU

## Key Scripts

- `scripts/hyperbolic_proxy.py`: Hyperbolic inference proxy (inference-only)
- `scripts/mlnode_poc_manager.py`: Official MLNode container manager for PoC
- `scripts/3_poc_scheduler.py`: Automated PoC orchestration with official MLNode
- `scripts/1_poc_monitor.py`: Blockchain monitoring for PoC timing
- `scripts/2_vastai_manager.py`: Vast.ai API manager
- `test_mlnode_poc_integration.py`: Integration test for official MLNode PoC

## FAQ

**Does this use the official MLNode PoC implementation?**
Yes! The automation now deploys the official MLNode Docker container
(`ghcr.io/product-science/mlnode`) which includes the complete PoC implementation.
This ensures 100% compatibility with the Gonka network protocol.

**Can I run the MLNode inference without a GPU?**
Yes. The Hyperbolic proxy runs on a CPU-only VPS and forwards inference to the
Hyperbolic API. GPUs are only required for PoC runs via Vast.ai.

**Do I still need Vast.ai?**
Yes, for PoC sprints. Inference is fully offloaded to Hyperbolic, but PoC requires
GPU compute. The automation rents GPUs only during PoC windows (~15 minutes every
few hours).

**How does PoC work with the official MLNode?**
The Network Node automatically calls the MLNode PoC endpoints when PoC starts.
The MLNode container handles all PoC computation, validation, and callbacks using
the official implementation from `mlnode/packages/pow`.

## License

MIT
