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

Create `config/.env` (use `config/.env.example` as a template if present) and
set your keys. Example:

```bash
# Hyperbolic API (inference)
HYPERBOLIC_API_KEY=your_hyperbolic_api_key_here
HYPERBOLIC_MODEL=Qwen/QwQ-32B

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
admin API.

```bash
source venv/bin/activate
python3 scripts/hyperbolic_proxy.py
```

Default settings (override via environment variables):
- `NODE_ID` (default: `hyperbolic-proxy-1`)
- `VPS_IP` (default: `198.74.55.121`)
- `PROXY_PORT` (default: `8080`)
- `MODEL_NAME` (default: `Qwen/QwQ-32B`)
- `GONKA_ADMIN_API_URL` (default: `http://localhost:9200`)
- `INFERENCE_SEGMENT` (default: `/v1`)
- `POC_SEGMENT` (default: `/api/v1`)
- `HARDWARE_TYPE` (default: `Hyperbolic-API`)
- `HARDWARE_COUNT` (default: `1`)

### Step 4: Start PoC scheduler (Vast.ai)

```bash
source venv/bin/activate
python3 scripts/3_poc_scheduler.py
```

The scheduler monitors the chain and spins up Vast.ai GPUs for PoC windows.

## Hybrid Run

Use the helper scripts to start or stop both the Hyperbolic proxy and PoC
scheduler together. The start script loads `config/.env`, activates the
virtualenv, and writes logs to `logs/`.

```bash
./scripts/start_hybrid.sh
```

To stop both services:

```bash
./scripts/stop_hybrid.sh
```

For a systemd example, see `scripts/systemd/gonka-hybrid.service`.

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
