#!/usr/bin/env python3
"""
Hyperbolic Proxy for Gonka Network
Implements all required ML Node API endpoints
"""

import os
import json
import hashlib
import httpx
import logging
import uuid
from random import randint
from fastapi import FastAPI, Request, HTTPException, Body
from fastapi.responses import StreamingResponse, JSONResponse
import uvicorn
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "config", ".env"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Configuration
NODE_ID = os.getenv("MLNODE_ID", os.getenv("NODE_ID", "hyperbolic-proxy-1"))
VPS_IP = os.getenv("VPS_IP", "198.74.55.121")
PROXY_PORT = int(os.getenv("HYPERBOLIC_PROXY_PORT", os.getenv("PROXY_PORT", "8080")))
HYPERBOLIC_API_KEY = os.getenv("HYPERBOLIC_API_KEY")
INFERENCE_MODEL = os.getenv(
    "MLNODE_INFERENCE_MODEL",
    os.getenv("HYPERBOLIC_MODEL", os.getenv("MODEL_NAME", "Qwen/QwQ-32B")),
)
MODEL_NAME = INFERENCE_MODEL
HYPERBOLIC_BASE_URL = os.getenv("HYPERBOLIC_BASE_URL", "https://api.hyperbolic.xyz")
GONKA_ADMIN_API = os.getenv("GONKA_ADMIN_API_URL", os.getenv("GONKA_ADMIN_API", "http://localhost:9200"))
INFERENCE_SEGMENT = os.getenv("INFERENCE_SEGMENT", "/v1")
POC_SEGMENT = os.getenv("POC_SEGMENT", "/api/v1")
HARDWARE_TYPE = os.getenv("HARDWARE_TYPE", "Hyperbolic-API")
HARDWARE_COUNT = int(os.getenv("HARDWARE_COUNT", "1"))
EXECUTOR_BASE_URL = os.getenv("EXECUTOR_BASE_URL", "")
EXECUTOR_INFERENCE_PATH = os.getenv("EXECUTOR_INFERENCE_PATH", "/v1/chat/completions")
INFERENCE_FORWARD_TIMEOUT = float(os.getenv("INFERENCE_FORWARD_TIMEOUT", "300"))
ENABLE_TRANSFER_ROUTING = os.getenv("ENABLE_TRANSFER_ROUTING", "true").lower() == "true"
TRANSFER_ADDRESS = os.getenv("TRANSFER_ADDRESS", "")
REQUESTER_ADDRESS = os.getenv("REQUESTER_ADDRESS", "")
REQUIRE_TRANSFER_SIGNATURE = os.getenv("REQUIRE_TRANSFER_SIGNATURE", "false").lower() == "true"

# Node state management
class NodeState:
    def __init__(self):
        self.status = "INFERENCE"  # STOPPED, INFERENCE, POC
        self.ready = True
        self.last_request = None
    
    def to_dict(self):
        return {
            "state": self.status,
            "ready": self.ready,
            "last_request": self.last_request
        }

node_state = NodeState()

app = FastAPI(title="Hyperbolic Proxy for Gonka")


def normalize_hyperbolic_base_url(raw_url: str) -> str:
    normalized = raw_url.rstrip("/")
    if normalized.endswith("/v1"):
        normalized = normalized[:-3]
    return normalized or "https://api.hyperbolic.xyz"


HYPERBOLIC_BASE_URL = normalize_hyperbolic_base_url(HYPERBOLIC_BASE_URL)
logger.info("Hyperbolic Proxy using inference model: %s", MODEL_NAME)


def generate_sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def build_executor_url() -> str:
    base_url = EXECUTOR_BASE_URL.rstrip("/")
    path = EXECUTOR_INFERENCE_PATH if EXECUTOR_INFERENCE_PATH.startswith("/") else f"/{EXECUTOR_INFERENCE_PATH}"
    return f"{base_url}{path}" if base_url else ""


def safe_int(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None

# ============================================================================
# Gonka ML Node Required Endpoints
# ============================================================================

@app.middleware("http")
async def normalize_duplicate_api_path(request: Request, call_next):
    path = request.scope.get("path", "")
    if "/api/v1/api/v1" in path:
        request.scope["path"] = path.replace("/api/v1/api/v1", "/api/v1", 1)
    return await call_next(request)

@app.get("/health")
@app.get("/api/v1/health")
@app.get("/{version}/health")
@app.get("/{version}/v1/health")
@app.get("/{version}/api/v1/health")
@app.get("/v3.0.8/api/v1/health")
@app.get("/v3.0.8/health")
async def health_check(version: str | None = None):
    """Health check endpoint"""
    return {
        "status": "healthy",
        "node_id": NODE_ID,
        "model": MODEL_NAME,
        "state": node_state.status
    }

@app.get("/api/v1/state")
@app.get("/{version}/api/v1/state")
@app.get("/v3.0.8/api/v1/state")
async def get_state(version: str | None = None):
    """Return current node state"""
    return node_state.to_dict()

@app.post("/api/v1/stop")
@app.post("/{version}/api/v1/stop")
@app.post("/v3.0.8/api/v1/stop")
async def stop_node(version: str | None = None):
    """Stop the node (transition to STOPPED state)"""
    print(f"🛑 Stop request received at {datetime.now()}")
    node_state.status = "STOPPED"
    node_state.ready = False
    return node_state.to_dict()

@app.post("/api/v1/inference/up")
@app.post("/{version}/api/v1/inference/up")
@app.post("/v3.0.8/api/v1/inference/up")
async def inference_up(version: str | None = None):
    """Mark node as ready for inference"""
    print(f"✅ Inference UP request received at {datetime.now()}")
    node_state.status = "INFERENCE"
    node_state.ready = True
    return node_state.to_dict()

@app.post("/api/v1/inference/down")
@app.post("/{version}/api/v1/inference/down")
@app.post("/v3.0.8/api/v1/inference/down")
async def inference_down(version: str | None = None):
    """Mark node as not ready for inference"""
    print(f"🛑 Inference DOWN request received at {datetime.now()}")
    node_state.status = "STOPPED"
    node_state.ready = False
    return node_state.to_dict()

# ============================================================================
# NOTE: PoC (Proof of Compute) endpoints are NOT implemented in this proxy.
# This proxy is INFERENCE-ONLY using Hyperbolic API.
#
# For PoC operations, the Network Node will automatically route to the
# official MLNode containers deployed on Vast.ai GPUs (managed by the scheduler).
# ============================================================================

@app.post("/api/v1/train/start")
@app.post("/{version}/api/v1/train/start")
@app.post("/v3.0.8/api/v1/train/start")
async def train_start(request: dict = Body(...), version: str | None = None):
    """Start training (no-op for proxy)"""
    print(f"📚 Train start request: {json.dumps(request, indent=2)}")
    return {
        "status": "acknowledged",
        "timestamp": datetime.now().isoformat()
    }

@app.post("/api/v1/train/stop")
@app.post("/{version}/api/v1/train/stop")
@app.post("/v3.0.8/api/v1/train/stop")
async def train_stop(version: str | None = None):
    """Stop training (no-op for proxy)"""
    return {
        "status": "stopped",
        "timestamp": datetime.now().isoformat()
    }

@app.get("/api/v1/train/status")
@app.get("/{version}/api/v1/train/status")
@app.get("/v3.0.8/api/v1/train/status")
async def train_status(version: str | None = None):
    """Return training status"""
    return {
        "status": "idle",
        "timestamp": datetime.now().isoformat()
    }

@app.post("/api/v1/models/status")
@app.post("/{version}/api/v1/models/status")
@app.post("/v3.0.8/api/v1/models/status")
async def models_status(request: dict = Body(...), version: str | None = None):
    """Return status of requested models"""
    print(f"📋 Models status request: {json.dumps(request, indent=2)}")
    
    # Handle both request formats:
    # 1. {"models": ["model1", "model2"]}
    # 2. {"hf_repo": "model_name", "hf_commit": "..."}
    
    if "hf_repo" in request:
        # Single model check format
        requested_model = request.get("hf_repo")
        is_available = (requested_model == MODEL_NAME)
        
        return {
            "hf_repo": requested_model,
            "hf_commit": request.get("hf_commit"),
            "status": "ready" if is_available else "unavailable",
            "loaded": is_available,
            "backend": "hyperbolic-api" if is_available else None
        }
    else:
        # Multiple models format
        requested_models = request.get("models", [MODEL_NAME])
        
        status = {}
        for model in requested_models:
            if model == MODEL_NAME:
                status[model] = {
                    "status": "ready",
                    "loaded": True,
                    "backend": "hyperbolic-api"
                }
            else:
                status[model] = {
                    "status": "unavailable",
                    "loaded": False
                }
        
        return {"models": status}

@app.get("/api/v1/gpu/devices")
@app.get("/{version}/api/v1/gpu/devices")
@app.get("/v3.0.8/api/v1/gpu/devices")
async def gpu_devices(version: str | None = None):
    """Return GPU device information"""
    print(f"🖥️  GPU devices request at {datetime.now()}")
    
    # For Hyperbolic proxy, report virtual GPU info
    # This is API-backed so we simulate a high-end GPU
    return {
        "devices": [
            {
                "id": 0,
                "name": "Hyperbolic API (Virtual H100)",
                "memory_total": 80000,  # 80GB (H100 equivalent)
                "memory_free": 80000,
                "utilization": 0,
                "temperature": 0
            }
        ],
        "count": 1,
        "backend": "hyperbolic-api"
    }

# ============================================================================
# OpenAI-Compatible Inference Endpoint (proxies to Hyperbolic)
# ============================================================================

@app.post("/v1/chat/completions")
@app.post("/api/v1/chat/completions")
@app.post("/{version}/v1/chat/completions")
@app.post("/{version}/api/v1/chat/completions")
@app.post("/v3.0.8/v1/chat/completions")
async def chat_completions(request: Request, version: str | None = None):
    """Proxy chat completions to Hyperbolic API or forward to an executor."""

    # Update node state
    node_state.last_request = datetime.now().isoformat()

    try:
        body_bytes = await request.body()
        if not body_bytes:
            raise HTTPException(status_code=400, detail="Empty request body")

        body = json.loads(body_bytes)
        is_streaming = body.get("stream", False)

        inference_id = request.headers.get("X-Inference-Id")
        seed_header = request.headers.get("X-Seed")
        timestamp = int(datetime.now().timestamp())

        if ENABLE_TRANSFER_ROUTING and not (inference_id and seed_header):
            executor_url = build_executor_url()
            if not executor_url:
                raise HTTPException(status_code=502, detail="EXECUTOR_BASE_URL not configured")

            prompt_hash = generate_sha256_hex(body_bytes)
            forward_headers = {
                "Content-Type": request.headers.get("content-type", "application/json"),
                "Authorization": request.headers.get("authorization", ""),
                "X-Inference-Id": inference_id or str(uuid.uuid4()),
                "X-Seed": seed_header or str(randint(1, 2_000_000_000)),
                "X-Timestamp": str(timestamp),
                "X-Prompt-Hash": prompt_hash,
            }

            if TRANSFER_ADDRESS:
                forward_headers["X-Transfer-Address"] = TRANSFER_ADDRESS
            if REQUESTER_ADDRESS:
                forward_headers["X-Requester-Address"] = REQUESTER_ADDRESS
            if request.headers.get("x-requester-address"):
                forward_headers["X-Requester-Address"] = request.headers.get("x-requester-address")
            if request.headers.get("x-ta-signature"):
                forward_headers["X-TA-Signature"] = request.headers.get("x-ta-signature")

            if REQUIRE_TRANSFER_SIGNATURE and not forward_headers.get("X-TA-Signature"):
                raise HTTPException(status_code=400, detail="Missing X-TA-Signature for transfer request")

            async with httpx.AsyncClient(timeout=INFERENCE_FORWARD_TIMEOUT) as client:
                if is_streaming:
                    async def stream_generator():
                        async with client.stream(
                            "POST",
                            executor_url,
                            content=body_bytes,
                            headers=forward_headers,
                        ) as response:
                            if response.status_code != 200:
                                error_text = await response.aread()
                                raise HTTPException(
                                    status_code=response.status_code,
                                    detail=f"Executor error: {error_text.decode()}",
                                )
                            async for chunk in response.aiter_bytes():
                                yield chunk

                    return StreamingResponse(stream_generator(), media_type="text/event-stream")

                response = await client.post(
                    executor_url,
                    content=body_bytes,
                    headers=forward_headers,
                )
                if response.status_code != 200:
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"Executor error: {response.text}",
                    )
                return JSONResponse(content=response.json())

        if not HYPERBOLIC_API_KEY:
            raise HTTPException(status_code=500, detail="HYPERBOLIC_API_KEY not configured")

        # Override model to ensure we use the configured one
        body["model"] = MODEL_NAME

        seed_value = safe_int(seed_header)
        if seed_value is not None:
            body["seed"] = seed_value

        print(f"📨 Inference request: {body.get('messages', [{}])[0].get('content', '')[:100]}...")

        # Prepare request to Hyperbolic
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {HYPERBOLIC_API_KEY}",
        }

        async with httpx.AsyncClient(timeout=INFERENCE_FORWARD_TIMEOUT) as client:
            if is_streaming:
                # Handle streaming response
                async def stream_generator():
                    async with client.stream(
                        "POST",
                        f"{HYPERBOLIC_BASE_URL}/v1/chat/completions",
                        json=body,
                        headers=headers,
                    ) as response:
                        if response.status_code != 200:
                            error_text = await response.aread()
                            raise HTTPException(
                                status_code=response.status_code,
                                detail=f"Hyperbolic API error: {error_text.decode()}",
                            )

                        async for chunk in response.aiter_bytes():
                            yield chunk

                return StreamingResponse(stream_generator(), media_type="text/event-stream")

            # Handle non-streaming response
            response = await client.post(
                f"{HYPERBOLIC_BASE_URL}/v1/chat/completions",
                json=body,
                headers=headers,
            )

            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Hyperbolic API error: {response.text}",
                )

            return JSONResponse(content=response.json())

    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Request timed out")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON request body")
    except Exception as e:
        print(f"❌ Error proxying request: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# Registration with Gonka Network
# ============================================================================

async def register_proxy_with_admin_api():
    """Register proxy node with Network Node Admin API (official registration)"""

    print(f"\n📋 Registering proxy node with Network Node Admin API...")
    print(f"   Node ID: {NODE_ID}")
    print(f"   Host: {VPS_IP}")
    print(f"   Port: {PROXY_PORT}")
    print(f"   Model: {MODEL_NAME}")
    print(f"   Admin API: {GONKA_ADMIN_API}")

    # Build registration payload per official Gonka docs
    # Format must match the Network Node Admin API expectations
    registration_payload = {
        "id": NODE_ID,
        "host": VPS_IP,
        "inference_port": PROXY_PORT,
        "inference_segment": INFERENCE_SEGMENT,
        "poc_port": PROXY_PORT,
        "poc_segment": POC_SEGMENT,
        "max_concurrent": 10,
        "models": {
            MODEL_NAME: {
                "args": []  # No vLLM args needed for Hyperbolic API proxy
            }
        },
        "hardware": [
            {
                "type": HARDWARE_TYPE,
                "count": HARDWARE_COUNT
            }
        ]
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{GONKA_ADMIN_API}/admin/v1/nodes",
                json=registration_payload,
                headers={"Content-Type": "application/json"}
            )

            if response.status_code in [200, 201]:
                print(f"✅ Registered with Admin API")
                print(f"   Response: {response.status_code}")
                return True
            elif response.status_code == 404:
                # Admin API not found - likely using on-chain registration only
                print(f"ℹ️  Admin API not accessible at {GONKA_ADMIN_API}")
                print(f"   Using on-chain registration only (this is normal)")
                return True  # Non-fatal
            elif response.status_code == 409:
                # Node already registered
                print(f"ℹ️  Node already registered in Admin API")
                return True  # Non-fatal
            else:
                print(f"⚠️  Registration returned status {response.status_code}")
                try:
                    error_detail = response.json()
                    print(f"   Error: {error_detail.get('error', response.text[:200])}")
                except:
                    print(f"   Response: {response.text[:200]}")
                return True  # Non-fatal, allow proxy to start

    except Exception as e:
        print(f"⚠️  Admin API registration failed: {str(e)}")
        print(f"   Proxy will use on-chain registration only")
        return True  # Non-fatal, allow proxy to start


async def register_with_gonka():
    """Verify Gonka Network on-chain registration (informational only)"""

    # Get the Gonka host address from environment
    gonka_address = os.getenv("GONKA_HOST_ADDRESS")

    if not gonka_address:
        print("\n⚠️  GONKA_HOST_ADDRESS not set - skipping registration verification")
        print("   This proxy will run but may not be discoverable by the Gonka network")
        print(f"   Proxy endpoint: http://{VPS_IP}:{PROXY_PORT}")
        return True  # Non-fatal, allow proxy to start

    # Determine the correct Gonka API URL
    # Use GONKA_ADMIN_API if it points to a Gonka node, otherwise use default seed node
    network_api = GONKA_ADMIN_API
    if "localhost" in network_api or "127.0.0.1" in network_api:
        # localhost won't work for blockchain API, use public seed node
        network_api = os.getenv("GONKA_NETWORK_NODE_URL", "http://node2.gonka.ai:8000")

    print(f"\n🔗 Verifying on-chain registration with Gonka Network...")
    print(f"   Address: {gonka_address}")
    print(f"   Network: {network_api}")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Check participant registration on Gonka blockchain
            response = await client.get(
                f"{network_api}/v1/participants/{gonka_address}"
            )

            if response.status_code == 200:
                result = response.json()
                print(f"✅ Verified on-chain registration")
                print(f"   Public Key: {result.get('pubkey', 'N/A')}")
                print(f"   Proxy endpoint: http://{VPS_IP}:{PROXY_PORT}")
                return True
            elif response.status_code == 404:
                print(f"⚠️  Address not registered on Gonka blockchain")
                print(f"   To register, follow: https://gonka.ai/host/quickstart/")
                print(f"   Proxy will run but won't receive PoC tasks")
                return True  # Non-fatal, allow proxy to start
            else:
                print(f"⚠️  Could not verify registration: {response.status_code}")
                return True  # Non-fatal, allow proxy to start

    except Exception as e:
        print(f"⚠️  Registration verification failed: {str(e)}")
        print(f"   Proxy will start anyway at http://{VPS_IP}:{PROXY_PORT}")
        return True  # Non-fatal, allow proxy to start

# ============================================================================
# Startup and Main
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Register proxy with Gonka on startup"""
    # Step 1: Register with Network Node Admin API (official node registration)
    await register_proxy_with_admin_api()

    # Step 2: Verify on-chain registration (informational)
    await register_with_gonka()

def main():
    """Main entry point"""
    
    print("=" * 70)
    print("  Hyperbolic Proxy Server for Gonka (INFERENCE ONLY)")
    print("=" * 70)
    print(f"📍 Configuration:")
    print(f"   Node ID: {NODE_ID}")
    print(f"   VPS IP: {VPS_IP}")
    print(f"   Port: {PROXY_PORT}")
    print(f"   Model: {MODEL_NAME}")
    print(f"   Admin API: {GONKA_ADMIN_API}")
    print(f"   Inference segment: {INFERENCE_SEGMENT}")
    print(f"\n⚠️  NOTE: This proxy handles INFERENCE ONLY")
    print(f"   PoC operations are handled by official MLNode containers on Vast.ai GPUs")
    print(f"   The scheduler (3_poc_scheduler.py) manages PoC automation")
    print(f"\n🚀 Starting server on port {PROXY_PORT}...")
    print(f"   Endpoints:")
    print(f"     • GET  /health")
    print(f"     • GET  /api/v1/state")
    print(f"     • POST /api/v1/stop")
    print(f"     • POST /api/v1/inference/up")
    print(f"     • POST /api/v1/models/status")
    print(f"     • GET  /api/v1/gpu/devices")
    print(f"     • POST /v1/chat/completions")
    print(f"   Press Ctrl+C to stop\n")
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=PROXY_PORT,
        log_level="info"
    )

if __name__ == "__main__":
    main()
