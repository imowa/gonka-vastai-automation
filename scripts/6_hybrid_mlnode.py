#!/usr/bin/env python3
"""
Hybrid MLNode Manager
- Routes inference requests to Hyperbolic API
- Handles PoC requests with Vast.ai GPU bursts
- Runs 24/7 on VPS with minimal resources
"""

import os
import time
import json
import logging
import asyncio
import threading
from typing import Dict, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
import uvicorn
from dotenv import load_dotenv

# Load your existing modules
import sys
sys.path.append('scripts')
from poc_scheduler import PoCScheduler
from hyperbolic_runner import HyperbolicAPIRunner
from mlnode_deployer import MLNodeDeployer

load_dotenv('config/.env')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class HybridConfig:
    """Configuration for hybrid MLNode"""
    # Network Node settings
    network_node_url: str
    admin_api_url: str
    
    # Hyperbolic settings
    hyperbolic_api_key: str
    hyperbolic_model: str
    
    # Vast.ai settings
    vastai_api_key: str
    max_gpu_price: float
    
    # MLNode settings
    mlnode_port: int = 8080
    inference_port: int = 5000
    node_id: str = "hybrid-mlnode"

class HybridMLNode:
    """
    Hybrid MLNode that combines:
    - Hyperbolic API for inference
    - Vast.ai GPU bursts for PoC
    - FastAPI server mimicking MLNode interface
    """
    
    def __init__(self, config: HybridConfig):
        self.config = config
        
        # Initialize components
        self.hyperbolic = HyperbolicAPIRunner(
            api_key=config.hyperbolic_api_key,
            model=config.hyperbolic_model
        )
        
        self.poc_scheduler = PoCScheduler()
        self.mlnode_deployer = MLNodeDeployer()
        
        # State tracking
        self.poc_active = False
        self.poc_instance_id = None
        self.last_poc_check = None
        
        # FastAPI app
        self.app = FastAPI(title="Hybrid MLNode")
        self._setup_routes()
        
        # Background monitor
        self.monitor_running = True
        self.monitor_thread = None
        
        logger.info("Hybrid MLNode initialized")
        logger.info(f"Inference model: {config.hyperbolic_model}")
        logger.info(f"Node ID: {config.node_id}")
    
    def _setup_routes(self):
        """Setup FastAPI routes that mimic MLNode interface"""
        
        @self.app.get("/health")
        async def health():
            """Health check endpoint"""
            return {
                "status": "healthy",
                "timestamp": datetime.utcnow().isoformat(),
                "node_type": "hybrid",
                "inference_backend": "hyperbolic",
                "poc_backend": "vastai_burst"
            }
        
        @self.app.get("/api/v1/models")
        async def list_models():
            """List available models"""
            return {
                "data": [
                    {
                        "id": self.config.hyperbolic_model,
                        "object": "model",
                        "created": int(time.time()),
                        "owned_by": "hyperbolic"
                    }
                ]
            }
        
        @self.app.post("/v1/chat/completions")
        async def chat_completions(request: Request):
            """Chat completions endpoint - routes to Hyperbolic"""
            try:
                request_data = await request.json()
                
                # Convert request format
                messages = []
                for msg in request_data.get('messages', []):
                    from hyperbolic_runner import ChatMessage
                    messages.append(ChatMessage(
                        role=msg['role'],
                        content=msg['content']
                    ))
                
                # Call Hyperbolic API
                response = self.hyperbolic.chat_completion(
                    messages=messages,
                    temperature=request_data.get('temperature', 0.7),
                    max_tokens=request_data.get('max_tokens', 2048),
                    stream=request_data.get('stream', False)
                )
                
                if request_data.get('stream', False):
                    return StreamingResponse(
                        self._stream_response(response),
                        media_type="text/event-stream"
                    )
                else:
                    return JSONResponse(response)
            
            except Exception as e:
                logger.error(f"Chat completion error: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.post("/v1/completions")
        async def completions(request: Request):
            """Text completions endpoint"""
            try:
                request_data = await request.json()
                
                response = self.hyperbolic.completion(
                    prompt=request_data.get('prompt', ''),
                    temperature=request_data.get('temperature', 0.7),
                    max_tokens=request_data.get('max_tokens', 2048),
                    stream=request_data.get('stream', False)
                )
                
                if request_data.get('stream', False):
                    return StreamingResponse(
                        self._stream_response(response),
                        media_type="text/event-stream"
                    )
                else:
                    return JSONResponse(response)
            
            except Exception as e:
                logger.error(f"Completion error: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        # PoC-related endpoints
        @self.app.post("/api/v1/pow/init")
        async def pow_init(request: Request):
            """Initialize PoC - triggers GPU rental"""
            try:
                request_data = await request.json()
                logger.info("PoC initialization requested")
                
                # Start GPU instance for PoC
                success = await self._start_poc_gpu()
                
                if success:
                    return {
                        "status": "OK",
                        "pow_status": "INITIALIZING",
                        "backend": "vastai_gpu"
                    }
                else:
                    raise HTTPException(status_code=500, detail="Failed to start PoC GPU")
            
            except Exception as e:
                logger.error(f"PoC init error: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/v1/pow/status")
        async def pow_status():
            """Get PoC status"""
            if self.poc_active and self.poc_instance_id:
                return {
                    "status": "RUNNING",
                    "instance_id": self.poc_instance_id,
                    "backend": "vastai_gpu"
                }
            else:
                return {
                    "status": "IDLE",
                    "backend": "hybrid_vps"
                }
        
        @self.app.post("/api/v1/pow/stop")
        async def pow_stop():
            """Stop PoC - destroys GPU instance"""
            try:
                success = await self._stop_poc_gpu()
                return {
                    "status": "OK",
                    "pow_status": "STOPPED" if success else "ERROR"
                }
            except Exception as e:
                logger.error(f"PoC stop error: {e}")
                return {"status": "ERROR", "detail": str(e)}
    
    async def _stream_response(self, response_generator):
        """Stream response from Hyperbolic"""
        try:
            for chunk in response_generator:
                yield f"data: {json.dumps(chunk)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.error(f"Streaming error: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    async def _start_poc_gpu(self) -> bool:
        """Start GPU instance for PoC computation"""
        if self.poc_active:
            logger.info("PoC GPU already active")
            return True
        
        try:
            logger.info("Starting PoC GPU instance...")
            
            # Find best GPU offer
            offer_id = self.poc_scheduler.select_best_gpu()
            if not offer_id:
                logger.error("No suitable GPU offers found")
                return False
            
            # Rent GPU
            instance_id = self.poc_scheduler.start_gpu_instance(offer_id)
            if not instance_id:
                logger.error("Failed to rent GPU instance")
                return False
            
            # Deploy MLNode on GPU
            # This would need SSH integration with your existing deployer
            logger.info(f"PoC GPU instance started: {instance_id}")
            self.poc_instance_id = instance_id
            self.poc_active = True
            
            return True
        
        except Exception as e:
            logger.error(f"Failed to start PoC GPU: {e}")
            return False
    
    async def _stop_poc_gpu(self) -> bool:
        """Stop GPU instance"""
        if not self.poc_active or not self.poc_instance_id:
            return True
        
        try:
            logger.info(f"Stopping PoC GPU instance: {self.poc_instance_id}")
            
            # Stop GPU instance
            self.poc_scheduler.stop_gpu_instance(self.poc_instance_id)
            
            self.poc_instance_id = None
            self.poc_active = False
            
            logger.info("PoC GPU instance stopped")
            return True
        
        except Exception as e:
            logger.error(f"Failed to stop PoC GPU: {e}")
            return False
    
    def start_monitor(self):
        """Start background PoC monitoring"""
        def monitor_loop():
            while self.monitor_running:
                try:
                    self._check_poc_status()
                    time.sleep(60)  # Check every minute
                except Exception as e:
                    logger.error(f"Monitor error: {e}")
                    time.sleep(30)
        
        self.monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        self.monitor_thread.start()
        logger.info("PoC monitor started")
    
    def _check_poc_status(self):
        """Check if PoC sprint is needed"""
        try:
            # Use your existing monitor to check PoC timing
            # This would integrate with scripts/1_poc_monitor.py
            pass
        except Exception as e:
            logger.error(f"PoC status check failed: {e}")
    
    def run(self):
        """Run the hybrid MLNode server"""
        self.start_monitor()
        
        logger.info(f"Starting Hybrid MLNode on port {self.config.mlnode_port}")
        logger.info(f"Inference API on port {self.config.inference_port}")
        
        # Run FastAPI server
        uvicorn.run(
            self.app,
            host="0.0.0.0",
            port=self.config.mlnode_port,
            log_level="info"
        )
    
    def stop(self):
        """Stop the hybrid MLNode"""
        self.monitor_running = False
        if self.poc_active:
            asyncio.run(self._stop_poc_gpu())

def load_config() -> HybridConfig:
    """Load configuration from environment"""
    return HybridConfig(
        network_node_url=os.getenv('GONKA_NETWORK_NODE_URL', 'http://167.71.86.126:8000'),
        admin_api_url=os.getenv('GONKA_ADMIN_API_URL', 'http://localhost:9200'),
        hyperbolic_api_key=os.getenv('HYPERBOLIC_API_KEY'),
        hyperbolic_model=os.getenv('HYPERBOLIC_MODEL', 'Qwen2.5-72B'),
        vastai_api_key=os.getenv('VASTAI_API_KEY'),
        max_gpu_price=float(os.getenv('MAX_GPU_PRICE', '0.5')),
        node_id=os.getenv('MLNODE_ID', 'hybrid-mlnode')
    )

def main():
    """Main entry point"""
    print("\n" + "="*60)
    print("  Hybrid MLNode - Hyperbolic + Vast.ai")
    print("="*60)
    
    try:
        config = load_config()
        
        if not config.hyperbolic_api_key:
            print("❌ HYPERBOLIC_API_KEY not found in environment")
            return False
        
        if not config.vastai_api_key:
            print("❌ VASTAI_API_KEY not found in environment")
            return False
        
        # Test connections
        print("\n🔍 Testing connections...")
        
        # Test Hyperbolic
        hyperbolic = HyperbolicAPIRunner(api_key=config.hyperbolic_api_key)
        if hyperbolic.health_check():
            print("✅ Hyperbolic API connection successful")
        else:
            print("❌ Hyperbolic API connection failed")
            return False
        
        print(f"\n🚀 Starting Hybrid MLNode...")
        print(f"   Inference: Hyperbolic {config.hyperbolic_model}")
        print(f"   PoC: Vast.ai GPU bursts (max ${config.max_gpu_price}/hr)")
        print(f"   Listening on: 0.0.0.0:{config.mlnode_port}")
        
        # Start hybrid MLNode
        hybrid_node = HybridMLNode(config)
        hybrid_node.run()
        
    except KeyboardInterrupt:
        print("\n👋 Shutting down...")
        return True
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return False

if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)
