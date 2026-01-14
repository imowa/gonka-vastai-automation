#!/usr/bin/env python3
"""
PoC Scheduler
Orchestrates the complete PoC automation workflow:
1. Monitor blockchain for PoC timing
2. Rent GPU 30 minutes before PoC
3. Deploy Gonka MLNode
4. Run PoC Sprint
5. Stop GPU automatically
"""

import sys
import os
import time
import json
import logging
import requests
from datetime import datetime, timedelta
from typing import Optional, Dict
from dataclasses import dataclass
import importlib.util
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

# Load our custom modules
def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

poc_monitor_module = load_module("poc_monitor", "scripts/1_poc_monitor.py")
vastai_module = load_module("vastai_manager", "scripts/2_vastai_manager.py")

PoCMonitor = poc_monitor_module.PoCMonitor
VastAIManager = vastai_module.VastAIManager

from env_loader import load_env

load_env('config/.env')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/poc_scheduler.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class PoCSession:
    """Represents a PoC Sprint session"""
    epoch_id: int
    instance_id: Optional[int] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    status: str = "pending"  # pending, running, completed, failed
    total_cost: float = 0.0
    gpu_type: Optional[str] = None


class PoCScheduler:
    """Main scheduler for automated PoC execution"""
    
    def __init__(self):
        self.monitor = PoCMonitor()
        self.vastai = VastAIManager()
        
        # Configuration
        self.prep_time = int(os.getenv('POC_PREP_TIME', '1800'))  # 30 minutes
        self.max_duration = int(os.getenv('MAX_POC_DURATION', '10800'))  # 3 hours safety
        self.check_interval = int(os.getenv('POC_CHECK_INTERVAL', '300'))  # 5 minutes
        self.max_daily_spend = float(os.getenv('MAX_DAILY_SPEND', '2.0'))
        self.admin_api_url = os.getenv('GONKA_ADMIN_API_URL', 'http://localhost:9200')
        self.proxy_host = os.getenv("VPS_IP", "198.74.55.121")
        self.proxy_port = int(os.getenv("HYPERBOLIC_PROXY_PORT", os.getenv("PROXY_PORT", "8080")))
        self.proxy_health_path = os.getenv("PROXY_HEALTH_PATH", "/health")
        self.proxy_node_id = os.getenv("MLNODE_ID", os.getenv("NODE_ID", "hyperbolic-proxy-1"))
        self.proxy_model_name = os.getenv(
            "HYPERBOLIC_MODEL",
            os.getenv("MLNODE_MODEL", os.getenv("MODEL_NAME", "Qwen/QwQ-32B"))
        )
        self.proxy_inference_segment = os.getenv("INFERENCE_SEGMENT", "/v1")
        self.proxy_poc_segment = os.getenv("POC_SEGMENT", "/api/v1")
        self.proxy_hardware_type = os.getenv("HARDWARE_TYPE", "Hyperbolic-API")
        self.proxy_hardware_count = int(os.getenv("HARDWARE_COUNT", "1"))
        self.instance_ready_timeout = int(os.getenv("VASTAI_INSTANCE_READY_TIMEOUT", "1800"))
        self.instance_start_retries = int(os.getenv("VASTAI_START_RETRIES", "2"))
        self.search_retries = int(os.getenv("VASTAI_SEARCH_RETRIES", "3"))
        self.search_interval = int(os.getenv("VASTAI_SEARCH_INTERVAL", "300"))
        self.min_total_vram_gb = int(os.getenv("VASTAI_MIN_TOTAL_VRAM", "40"))
        self.vastai_docker_image = os.getenv(
            "DOCKER_IMAGE",
            os.getenv("VASTAI_DOCKER_IMAGE", "vllm/vllm-openai:latest"),
        )
        self.vastai_onstart_script = os.getenv("VASTAI_ONSTART_SCRIPT", "")
        
        # State
        self.current_session: Optional[PoCSession] = None
        self.daily_spend = 0.0
        self.last_reset_date = datetime.now().date()
        
        logger.info("PoC Scheduler initialized")
        logger.info(f"Prep time: {self.prep_time}s ({self.prep_time//60} minutes)")
        logger.info(f"Max duration: {self.max_duration}s ({self.max_duration//3600} hours)")
        logger.info(f"Check interval: {self.check_interval}s ({self.check_interval//60} minutes)")
        logger.info(f"Max daily spend: ${self.max_daily_spend}")
        logger.info(
            "Instance ready timeout: %ss (%s minutes)",
            self.instance_ready_timeout,
            self.instance_ready_timeout // 60,
        )
        logger.info("Instance start retries: %s", self.instance_start_retries)
        logger.info(
            "GPU search retries: %s (interval %ss)",
            self.search_retries,
            self.search_interval,
        )
        logger.info("Min total VRAM: %sGB", self.min_total_vram_gb)
    
    def reset_daily_spend(self):
        """Reset daily spend counter at midnight"""
        today = datetime.now().date()
        if today > self.last_reset_date:
            logger.info(f"Daily spend reset: ${self.daily_spend:.2f} → $0.00")
            self.daily_spend = 0.0
            self.last_reset_date = today
    
    def check_spending_limit(self) -> bool:
        """Check if we're within spending limits"""
        if self.daily_spend >= self.max_daily_spend:
            logger.warning(f"Daily spending limit reached: ${self.daily_spend:.2f}")
            return False
        return True
    
    def select_best_gpu(self, exclude_offer_ids: Optional[set] = None) -> Optional[int]:
        """
        Search for and select the best available GPU instance
        
        Returns:
            Offer ID if found, None otherwise
        """
        logger.info("Searching for available GPU instances...")
        valid_offers = []
        attempts = max(1, self.search_retries)

        for attempt in range(1, attempts + 1):
            blocked_offer_ids = self.vastai.get_blocked_offer_ids()
            blocked_host_ids = self.vastai.get_blocked_host_ids()
            if exclude_offer_ids:
                blocked_offer_ids = blocked_offer_ids.union(exclude_offer_ids)

            offers = self.vastai.search_offers(
                limit=5,
                exclude_offer_ids=blocked_offer_ids,
                exclude_host_ids=blocked_host_ids,
            )

            if not offers:
                logger.warning("No GPU instances available (attempt %s/%s)", attempt, attempts)
            else:
                # Filter by VRAM requirement
                valid_offers = [
                    o
                    for o in offers
                    if (o.gpu_ram * o.num_gpus) >= (self.min_total_vram_gb * 1000)
                ]
                if valid_offers:
                    break
                logger.warning(
                    "No instances with %sGB+ total VRAM found (attempt %s/%s)",
                    self.min_total_vram_gb,
                    attempt,
                    attempts,
                )
                logger.info("Available offers didn't meet VRAM requirements")

            if attempt < attempts:
                logger.info("Retrying GPU search in %ss...", self.search_interval)
                time.sleep(self.search_interval)

        if not valid_offers:
            logger.error("No suitable GPU instances available after %s attempts", attempts)
            return None
        
        # Select cheapest valid offer
        best_offer = valid_offers[0]
        logger.info(f"Selected: {best_offer}")
        logger.info(f"Cost estimate for 15 min: ${(best_offer.dph_total / 60) * 15:.3f}")
        
        return best_offer.id

    def start_gpu_instance_with_retries(
        self,
        preferred_offer_id: Optional[int] = None,
        docker_image: Optional[str] = None,
        onstart: Optional[str] = None,
        disk: Optional[int] = None,
    ) -> Optional[int]:
        """Start a GPU instance with retry logic and blocked offer tracking."""
        tried_offers = set()

        for attempt in range(1, self.instance_start_retries + 1):
            if preferred_offer_id and preferred_offer_id not in tried_offers:
                offer_id = preferred_offer_id
            else:
                offer_id = self.select_best_gpu(exclude_offer_ids=tried_offers)

            if not offer_id:
                logger.error("No GPU offer available for attempt %s", attempt)
                return None

            tried_offers.add(offer_id)
            logger.info(
                "GPU start attempt %s/%s using offer %s",
                attempt,
                self.instance_start_retries,
                offer_id,
            )

            instance_id = self.start_gpu_instance(
                offer_id,
                docker_image=docker_image,
                onstart=onstart,
                disk=disk,
            )
            if instance_id:
                return instance_id

            logger.warning("GPU start attempt %s failed for offer %s", attempt, offer_id)

        logger.error("All GPU start attempts failed after %s tries", self.instance_start_retries)
        return None

    def _proxy_base_url(self) -> str:
        return f"http://{self.proxy_host}:{self.proxy_port}"

    def check_inference_proxy_health(self) -> bool:
        """Check inference proxy health endpoint"""
        url = f"{self._proxy_base_url()}{self.proxy_health_path}"
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                logger.info(f"✅ Inference proxy healthy at {url}")
                return True
            logger.warning(f"⚠️ Inference proxy health check failed: {response.status_code} {response.text}")
            return False
        except requests.RequestException as e:
            logger.warning(f"⚠️ Inference proxy health check failed: {e}")
            return False

    def is_inference_proxy_registered(self) -> bool:
        """Check if inference proxy is registered with Network Node"""
        try:
            response = requests.get(f"{self.admin_api_url}/admin/v1/nodes", timeout=10)
            response.raise_for_status()
            nodes = response.json()
            for node_data in nodes:
                node_info = node_data.get('node', {})
                if node_info.get('id') == self.proxy_node_id:
                    return True
        except requests.RequestException as e:
            logger.warning(f"⚠️ Failed to check proxy registration: {e}")
        return False

    def register_inference_proxy(self) -> bool:
        """Register inference proxy with Network Node"""
        payload = {
            "id": self.proxy_node_id,
            "host": self.proxy_host,
            "inference_port": self.proxy_port,
            "inference_segment": self.proxy_inference_segment,
            "poc_port": self.proxy_port,
            "poc_segment": self.proxy_poc_segment,
            "max_concurrent": 100,
            "models": {
                self.proxy_model_name: {}
            },
            "hardware": [
                {"type": self.proxy_hardware_type, "count": self.proxy_hardware_count}
            ]
        }

        try:
            logger.info(f"Registering inference proxy node {self.proxy_node_id}")
            response = requests.post(
                f"{self.admin_api_url}/admin/v1/nodes",
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            logger.info(f"✅ Inference proxy registered: {self.proxy_node_id}")
            return True
        except requests.RequestException as e:
            logger.warning(f"⚠️ Failed to register inference proxy: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.warning(f"Response: {e.response.text}")
            return False

    def ensure_inference_proxy_registered(self) -> None:
        """Ensure inference proxy is registered, re-register if missing"""
        if self.is_inference_proxy_registered():
            logger.info("✅ Inference proxy already registered")
            return

        logger.warning("⚠️ Inference proxy not registered; attempting to register")
        self.register_inference_proxy()
    
    def start_gpu_instance(
        self,
        offer_id: int,
        docker_image: Optional[str] = None,
        onstart: Optional[str] = None,
        disk: Optional[int] = None,
    ) -> Optional[int]:
        """
        Start a GPU instance
        
        Returns:
            Instance ID if successful, None otherwise
        """
        logger.info(f"Creating instance from offer {offer_id}...")
        
        image = docker_image or self.vastai_docker_image
        disk = disk if disk is not None else int(os.getenv('VASTAI_DISK_SIZE', '50'))
        resolved_onstart = onstart
        if resolved_onstart is None:
            resolved_onstart = self.vastai_onstart_script.strip() or None
        logger.info("Using Vast.ai image: %s", image)
        if resolved_onstart:
            logger.info("Using custom onstart script (length: %s chars)", len(resolved_onstart))
        
        instance_id = self.vastai.create_instance(
            offer_id=offer_id,
            image=image,
            disk=disk,
            onstart=resolved_onstart
        )
        
        if not instance_id:
            logger.error("Failed to create instance")
            return None
        
        logger.info(f"Instance {instance_id} created, waiting for ready state...")
        
        # Wait for instance to be ready
        if not self.vastai.wait_for_ready(instance_id, timeout=self.instance_ready_timeout):
            logger.error(f"Instance {instance_id} failed to start")
            # Try to destroy failed instance
            self.vastai.destroy_instance(instance_id)
            return None
        
        return instance_id
    
    def run_poc_sprint(self, instance_id: int) -> bool:
        """
        Run PoC Sprint using remote vLLM on GPU
        Network Node talks directly to remote vLLM (no local MLNode needed)
        
        Returns:
            True if successful, False otherwise
        """
        logger.info(f"Running PoC Sprint with remote vLLM on instance {instance_id}")
        
        vllm_manager = None
        ssh_info = None
        vllm_host = None
        registered = False

        try:
            # Import remote vLLM manager
            spec = importlib.util.spec_from_file_location("vllm_manager", "scripts/5_vllm_proxy_manager.py")
            vllm_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(vllm_module)
            RemoteVLLMManager = vllm_module.RemoteVLLMManager

            vllm_manager = RemoteVLLMManager()

            # Step 1: Get SSH connection to GPU
            logger.info("Step 1: Connecting to GPU instance...")
            ssh_info = vllm_manager.get_ssh_connection(self.vastai, instance_id)

            if not ssh_info:
                logger.error("Failed to get SSH connection")
                self.vastai.block_instance(instance_id, reason="ssh-info-unavailable")
                return False

            logger.info(f"✅ Connected: {ssh_info['host']}:{ssh_info['port']}")

            # Step 2: Start vLLM on remote GPU
            logger.info("Step 2: Starting vLLM on remote GPU...")
            vllm_host = vllm_manager.start_remote_vllm(ssh_info, instance_id)

            if not vllm_host:
                logger.error("Failed to start vLLM")
                self.vastai.block_instance(instance_id, reason="vllm-start-failed")
                return False

            logger.info(f"✅ vLLM ready at {vllm_host}")

            # Step 3: Register remote vLLM as MLNode
            logger.info("Step 3: Registering remote vLLM with Network Node...")
            if not self.check_inference_proxy_health():
                logger.warning("⚠️ Inference proxy is down; proceeding with PoC registration")
            if not vllm_manager.register_remote_mlnode(vllm_host, instance_id):
                logger.error("Failed to register remote MLNode")
                return False

            registered = True
            logger.info("✅ Remote MLNode registered")

            # Step 4: Wait for PoC to complete
            logger.info("Step 4: Monitoring PoC progress...")
            success = vllm_manager.wait_for_poc_completion(instance_id, timeout=900)

            if success:
                logger.info("✅ PoC Sprint completed!")
            else:
                logger.warning("⚠️  PoC Sprint timed out")

            return success

        except Exception as e:
            logger.error(f"Error during PoC Sprint: {e}", exc_info=True)
            self.vastai.block_instance(instance_id, reason="poc-sprint-error")
            return False
        finally:
            if vllm_manager and registered:
                logger.info("Unregistering remote MLNode...")
                vllm_manager.unregister_remote_mlnode(instance_id)
            if vllm_manager and ssh_info:
                logger.info("Stopping remote vLLM...")
                vllm_manager.stop_remote_vllm(ssh_info)
            self.ensure_inference_proxy_registered()
            logger.info("Cleanup complete")
    
    def stop_gpu_instance(self, instance_id: int) -> bool:
        """Stop and destroy GPU instance"""
        logger.info(f"Stopping instance {instance_id}...")
        
        # Get final cost
        cost = self.vastai.get_instance_cost(instance_id)
        if cost:
            logger.info(f"Total cost for this session: ${cost:.3f}")
            self.daily_spend += cost
            if self.current_session:
                self.current_session.total_cost = cost
        
        # Stop the instance
        success = self.vastai.destroy_instance(instance_id)
        
        if success:
            logger.info(f"✅ Instance {instance_id} stopped")
        else:
            logger.warning(f"Failed to stop instance {instance_id}")
        
        return success
    
    def execute_poc_cycle(self, epoch_id: int):
        """Execute a complete PoC cycle"""
        logger.info("="*60)
        logger.info(f"Starting PoC cycle for epoch {epoch_id}")
        logger.info("="*60)
        
        # Create session
        self.current_session = PoCSession(epoch_id=epoch_id)
        self.current_session.start_time = time.time()
        self.current_session.status = "running"
        
        try:
            # Step 1: Check spending limit
            if not self.check_spending_limit():
                logger.error("Cannot start PoC: spending limit reached")
                self.current_session.status = "failed"
                return
            
            # Step 2: Select GPU
            instance_id = self.start_gpu_instance_with_retries()
            if not instance_id:
                logger.error("Cannot start PoC: instance creation failed")
                self.current_session.status = "failed"
                return
            
            self.current_session.instance_id = instance_id
            
            # Step 4: Run PoC Sprint
            success = self.run_poc_sprint(instance_id)
            
            if success:
                self.current_session.status = "completed"
                logger.info("✅ PoC cycle completed successfully")
            else:
                self.current_session.status = "failed"
                logger.error("❌ PoC cycle failed")
            
        except Exception as e:
            logger.error(f"Error during PoC cycle: {e}", exc_info=True)
            self.current_session.status = "failed"
        
        finally:
            # Always stop the GPU instance
            if self.current_session.instance_id:
                self.stop_gpu_instance(self.current_session.instance_id)
            
            self.current_session.end_time = time.time()
            duration = self.current_session.end_time - self.current_session.start_time
            
            logger.info("="*60)
            logger.info(f"PoC cycle summary:")
            logger.info(f"  Status: {self.current_session.status}")
            logger.info(f"  Duration: {duration/60:.1f} minutes")
            logger.info(f"  Cost: ${self.current_session.total_cost:.3f}")
            logger.info(f"  Daily spend: ${self.daily_spend:.2f} / ${self.max_daily_spend}")
            logger.info("="*60)
    
    def run(self):
        """Main scheduler loop"""
        logger.info("="*60)
        logger.info("  PoC Scheduler Started")
        logger.info("="*60)
        logger.info("")
        logger.info("Monitoring blockchain for PoC timing...")
        logger.info(f"Will start GPU {self.prep_time//60} minutes before PoC")
        logger.info("")
        
        last_epoch = None
        
        while True:
            try:
                # Reset daily spend at midnight
                self.reset_daily_spend()
                
                # Get blockchain status
                status = self.monitor.get_status()
                
                if status['status'] != 'active':
                    logger.error("Cannot fetch blockchain data")
                    time.sleep(60)
                    continue
                
                current_epoch = status['current_epoch']
                next_epoch = status['next_epoch']
                seconds_to_poc = status['seconds_to_poc']
                should_start = status['should_start_gpu']
                
                # Log status
                hours = seconds_to_poc // 3600
                minutes = (seconds_to_poc % 3600) // 60
                logger.info(f"Epoch {current_epoch} | Phase: {status['current_phase']} | Next PoC: {hours}h {minutes}m")
                
                # Check if we should start GPU
                if should_start and next_epoch != last_epoch:
                    logger.warning(f"🚨 PoC Sprint approaching! Starting GPU...")
                    self.execute_poc_cycle(next_epoch)
                    last_epoch = next_epoch
                elif should_start:
                    logger.info("Already processed this epoch, waiting for next...")
                
            except KeyboardInterrupt:
                logger.info("\n⚠️  Shutdown requested")
                if self.current_session and self.current_session.instance_id:
                    logger.info("Stopping active GPU instance...")
                    self.stop_gpu_instance(self.current_session.instance_id)
                break
            
            except Exception as e:
                logger.error(f"Error in main loop: {e}", exc_info=True)
            
            # Wait before next check
            time.sleep(self.check_interval)


if __name__ == "__main__":
    try:
        # Create logs directory if it doesn't exist
        os.makedirs('logs', exist_ok=True)
        
        scheduler = PoCScheduler()
        scheduler.run()
    
    except KeyboardInterrupt:
        logger.info("\nShutdown complete")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
