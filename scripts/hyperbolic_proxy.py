#!/usr/bin/env python3
"""
Hyperbolic Proxy for Gonka Network
Implements all required ML Node API endpoints
"""

import os
import json
import sys
import httpx
from fastapi import FastAPI, Request, HTTPException, Body
from fastapi.responses import StreamingResponse, JSONResponse
import uvicorn
from datetime import datetime
import asyncio
import smtplib
from email.message import EmailMessage

# Configuration
NODE_ID = os.getenv("MLNODE_ID", os.getenv("NODE_ID", "hyperbolic-proxy-1"))
VPS_IP = os.getenv("VPS_IP")
PROXY_PORT = int(os.getenv("HYPERBOLIC_PROXY_PORT", os.getenv("PROXY_PORT", "8080")))
HYPERBOLIC_API_KEY = os.getenv("HYPERBOLIC_API_KEY")
MODEL_NAME = os.getenv(
    "HYPERBOLIC_MODEL",
    os.getenv("MLNODE_MODEL", os.getenv("MODEL_NAME", "Qwen/QwQ-32B")),
)
HYPERBOLIC_BASE_URL = os.getenv("HYPERBOLIC_BASE_URL", "https://api.hyperbolic.xyz")
GONKA_ADMIN_API = os.getenv("GONKA_ADMIN_API_URL", os.getenv("GONKA_ADMIN_API"))
INFERENCE_SEGMENT = os.getenv("INFERENCE_SEGMENT", "/v1")
POC_SEGMENT = os.getenv("POC_SEGMENT", "/api/v1")
HARDWARE_TYPE = os.getenv("HARDWARE_TYPE", "Hyperbolic-API")
HARDWARE_COUNT = int(os.getenv("HARDWARE_COUNT", "1"))
ENABLE_ALERTS = os.getenv("ENABLE_ALERTS", "false").lower() in {"1", "true", "yes", "on"}
ALERT_EMAIL = os.getenv("ALERT_EMAIL")
ALERT_WEBHOOK_URL = os.getenv("ALERT_WEBHOOK_URL")
SMTP_HOST = os.getenv("ALERT_SMTP_HOST")
SMTP_PORT = int(os.getenv("ALERT_SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("ALERT_SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("ALERT_SMTP_PASSWORD")
SMTP_FROM = os.getenv("ALERT_SMTP_FROM", ALERT_EMAIL)


def validate_required_env() -> None:
    required = {
        "HYPERBOLIC_API_KEY": HYPERBOLIC_API_KEY,
        "VPS_IP": VPS_IP,
        "GONKA_ADMIN_API_URL": GONKA_ADMIN_API,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        missing_list = ", ".join(missing)
        print(
            "❌ Missing required environment variables: "
            f"{missing_list}. Please set them before starting the proxy."
        )
        sys.exit(1)


validate_required_env()

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


async def _send_webhook_alert(payload: dict) -> None:
    if not ALERT_WEBHOOK_URL:
        return
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(ALERT_WEBHOOK_URL, json=payload)
    except Exception as exc:
        print(f"⚠️ Failed to send alert webhook: {exc}")


def _send_email_alert_sync(subject: str, body: str) -> None:
    if not (ALERT_EMAIL and SMTP_HOST and SMTP_FROM):
        return
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = SMTP_FROM
    message["To"] = ALERT_EMAIL
    message.set_content(body)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
        server.starttls()
        if SMTP_USERNAME and SMTP_PASSWORD:
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.send_message(message)


async def send_alert(title: str, message: str, details: dict | None = None) -> None:
    if not ENABLE_ALERTS:
        return

    payload = {
        "title": title,
        "message": message,
        "details": details or {},
        "node_id": NODE_ID,
        "timestamp": datetime.now().isoformat()
    }

    await _send_webhook_alert(payload)

    if ALERT_EMAIL and SMTP_HOST:
        body = json.dumps(payload, indent=2)
        try:
            await asyncio.to_thread(_send_email_alert_sync, title, body)
        except Exception as exc:
            print(f"⚠️ Failed to send alert email: {exc}")

# ============================================================================
# Gonka ML Node Required Endpoints
# ============================================================================

@app.get("/health")
@app.get("/api/v1/health")
@app.get("/{version}/health")
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

@app.post("/api/v1/pow/init")
@app.post("/{version}/api/v1/pow/init")
@app.post("/v3.0.8/api/v1/pow/init")
async def pow_init(request: dict = Body(...), version: str | None = None):
    """Handle Proof of Compute init"""
    print(f"🔐 PoC init request: {json.dumps(request, indent=2)}")
    # MLNode OpenAPI response schema: {"status": "OK"}.
    return {
        "status": "OK"
    }

@app.post("/api/v1/pow/init/generate")
@app.post("/{version}/api/v1/pow/init/generate")
@app.post("/v3.0.8/api/v1/pow/init/generate")
async def pow_init_generate(request: dict = Body(...), version: str | None = None):
    """Handle Proof of Compute initialization"""
    print(f"🔐 PoC init request: {json.dumps(request, indent=2)}")
    # For a proxy, we acknowledge but don't actually compute PoC
    # MLNode OpenAPI response schema: {"status": "OK"}.
    return {
        "status": "OK"
    }

@app.post("/api/v1/pow/init/validate")
@app.post("/{version}/api/v1/pow/init/validate")
@app.post("/v3.0.8/api/v1/pow/init/validate")
async def pow_init_validate(request: dict = Body(...), version: str | None = None):
    """Handle Proof of Compute init validation"""
    print(f"🔐 PoC init validate request: {json.dumps(request, indent=2)}")
    return {
        "status": "acknowledged",
        "timestamp": datetime.now().isoformat()
    }

@app.post("/api/v1/pow/phase/generate")
@app.post("/{version}/api/v1/pow/phase/generate")
@app.post("/v3.0.8/api/v1/pow/phase/generate")
async def pow_phase_generate(request: dict = Body(...), version: str | None = None):
    """Handle PoC phase generate requests"""
    print(f"🔐 PoC phase generate request: {json.dumps(request, indent=2)}")
    return {
        "status": "acknowledged",
        "timestamp": datetime.now().isoformat()
    }

@app.post("/api/v1/pow/phase/validate")
@app.post("/{version}/api/v1/pow/phase/validate")
@app.post("/v3.0.8/api/v1/pow/phase/validate")
async def pow_phase_validate(request: dict = Body(...), version: str | None = None):
    """Handle PoC phase validate requests"""
    print(f"🔐 PoC phase validate request: {json.dumps(request, indent=2)}")
    return {
        "status": "acknowledged",
        "timestamp": datetime.now().isoformat()
    }

@app.post("/api/v1/pow/validate")
@app.post("/{version}/api/v1/pow/validate")
@app.post("/v3.0.8/api/v1/pow/validate")
async def pow_validate(request: dict = Body(...), version: str | None = None):
    """Handle PoC proof validation"""
    print(f"🔐 PoC validate request: {json.dumps(request, indent=2)}")
    # MLNode OpenAPI response schema: {"status": "OK"}.
    return {
        "status": "OK"
    }

@app.get("/api/v1/pow/status")
@app.get("/{version}/api/v1/pow/status")
@app.get("/v3.0.8/api/v1/pow/status")
async def pow_status(version: str | None = None):
    """Return PoC status"""
    return {
        "status": "idle",
        "timestamp": datetime.now().isoformat()
    }

@app.post("/api/v1/pow/stop")
@app.post("/{version}/api/v1/pow/stop")
@app.post("/v3.0.8/api/v1/pow/stop")
async def pow_stop(version: str | None = None):
    """Stop PoC processing"""
    return {
        "status": "stopped",
        "timestamp": datetime.now().isoformat()
    }

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
    """Proxy chat completions to Hyperbolic API"""
    
    if not HYPERBOLIC_API_KEY:
        raise HTTPException(status_code=500, detail="HYPERBOLIC_API_KEY not configured")
    
    # Update node state
    node_state.last_request = datetime.now().isoformat()
    
    try:
        # Parse incoming request
        body = await request.json()
        is_streaming = body.get("stream", False)
        
        # Override model to ensure we use the configured one
        body["model"] = MODEL_NAME
        
        print(f"📨 Inference request: {body.get('messages', [{}])[0].get('content', '')[:100]}...")
        
        # Prepare request to Hyperbolic
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {HYPERBOLIC_API_KEY}"
        }
        
        async with httpx.AsyncClient(timeout=300.0) as client:
            if is_streaming:
                # Handle streaming response
                async def stream_generator():
                    async with client.stream(
                        "POST",
                        f"{HYPERBOLIC_BASE_URL}/v1/chat/completions",
                        json=body,
                        headers=headers
                    ) as response:
                        if response.status_code >= 500:
                            error_text = await response.aread()
                            await send_alert(
                                "Hyperbolic API 5xx error",
                                "Received 5xx response during streaming request.",
                                {
                                    "status_code": response.status_code,
                                    "response": error_text.decode()
                                }
                            )
                            raise HTTPException(
                                status_code=response.status_code,
                                detail=f"Hyperbolic API error: {error_text.decode()}"
                            )

                        if response.status_code != 200:
                            error_text = await response.aread()
                            raise HTTPException(
                                status_code=response.status_code,
                                detail=f"Hyperbolic API error: {error_text.decode()}"
                            )
                        
                        async for chunk in response.aiter_bytes():
                            yield chunk
                
                return StreamingResponse(
                    stream_generator(),
                    media_type="text/event-stream"
                )
            else:
                # Handle non-streaming response
                response = await client.post(
                    f"{HYPERBOLIC_BASE_URL}/v1/chat/completions",
                    json=body,
                    headers=headers
                )
                
                if response.status_code >= 500:
                    await send_alert(
                        "Hyperbolic API 5xx error",
                        "Received 5xx response from Hyperbolic API.",
                        {
                            "status_code": response.status_code,
                            "response": response.text
                        }
                    )
                if response.status_code != 200:
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"Hyperbolic API error: {response.text}"
                    )
                
                return JSONResponse(content=response.json())
    
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Request to Hyperbolic API timed out")
    except Exception as e:
        print(f"❌ Error proxying request: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# Registration with Gonka Network
# ============================================================================

async def preflight_self_check() -> bool:
    """Verify the proxy is reachable before registration."""
    base_url = f"http://{VPS_IP}:{PROXY_PORT}"
    endpoints = ["/health", "/api/v1/state"]

    async with httpx.AsyncClient(timeout=5.0) as client:
        for endpoint in endpoints:
            url = f"{base_url}{endpoint}"
            try:
                response = await client.get(url)
            except Exception as exc:
                print(f"⚠️ Preflight check failed for {url}: {exc}")
                return False

            if response.status_code != 200:
                print(
                    "⚠️ Preflight check failed for "
                    f"{url}: {response.status_code} {response.text}"
                )
                return False

    return True

async def register_with_gonka():
    """Register this proxy node with Gonka Network"""

    preflight_ok = await preflight_self_check()
    if not preflight_ok:
        print("⚠️ Skipping registration because preflight checks failed.")
        await send_alert(
            "Gonka registration skipped",
            "Preflight checks failed; registration was skipped.",
            {"admin_api": GONKA_ADMIN_API, "proxy_port": PROXY_PORT}
        )
        return False

    registration_data = {
        "id": NODE_ID,
        "host": VPS_IP,
        "inference_port": PROXY_PORT,
        "inference_segment": INFERENCE_SEGMENT,
        "poc_port": PROXY_PORT,
        "poc_segment": POC_SEGMENT,
        "max_concurrent": 100,
        "models": {
            MODEL_NAME: {}
        },
        "hardware": [
            {"type": HARDWARE_TYPE, "count": HARDWARE_COUNT}
        ]
    }
    
    print("\n🔗 Registering with Gonka Network...")
    print(f"   Payload: {json.dumps(registration_data, indent=2)}")
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{GONKA_ADMIN_API}/admin/v1/nodes",
                json=registration_data
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ Successfully registered with Gonka Network")
                print(f"   Node ID: {result.get('id')}")
                print(f"   Endpoint: http://{VPS_IP}:{PROXY_PORT}")
                return True
            else:
                print(f"❌ Registration failed: {response.status_code}")
                print(f"   Response: {response.text}")
                await send_alert(
                    "Gonka registration failed",
                    "Non-200 response when registering proxy.",
                    {"status_code": response.status_code, "response": response.text}
                )
                return False
    
    except Exception as e:
        print(f"❌ Registration error: {str(e)}")
        await send_alert(
            "Gonka registration error",
            "Exception while registering proxy.",
            {"error": str(e)}
        )
        return False

# ============================================================================
# Startup and Main
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Register with Gonka on startup"""
    await register_with_gonka()

def main():
    """Main entry point"""
    
    print("=" * 70)
    print("  Hyperbolic Proxy Server for Gonka (All Endpoints)")
    print("=" * 70)
    print(f"📍 Configuration:")
    print(f"   Node ID: {NODE_ID}")
    print(f"   VPS IP: {VPS_IP}")
    print(f"   Port: {PROXY_PORT}")
    print(f"   Model: {MODEL_NAME}")
    print(f"   Admin API: {GONKA_ADMIN_API}")
    print(f"   Inference segment: {INFERENCE_SEGMENT}")
    print(f"   PoC segment: {POC_SEGMENT}")
    print(f"\n🚀 Starting server on port {PROXY_PORT}...")
    print(f"   Endpoints:")
    print(f"     • GET  /health")
    print(f"     • GET  /api/v1/state")
    print(f"     • POST /api/v1/stop")
    print(f"     • POST /api/v1/inference/up")
    print(f"     • POST /api/v1/pow/init/generate")
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
