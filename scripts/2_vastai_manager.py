#!/usr/bin/env python3
"""
Vast.ai Manager
Manages GPU instances on Vast.ai for PoC Sprints
"""

import requests
import time
import json
from typing import Optional, Dict, List
import logging
from dataclasses import dataclass
import os
import sys
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from env_loader import load_env

load_env('config/.env')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class VastInstance:
    """Represents a Vast.ai GPU instance"""
    id: int
    status: str
    gpu_name: str
    num_gpus: int
    gpu_ram: int
    dph_total: float  # Price per hour
    inet_up: float
    inet_down: float
    host_id: int
    
    def __str__(self):
        return f"Instance {self.id}: {self.num_gpus}x {self.gpu_name} @ ${self.dph_total:.2f}/hr"


class VastAIManager:
    """Manager for Vast.ai GPU instances"""
    
    BASE_URL = "https://console.vast.ai/api/v0"
    FP8_CAPABLE_GPUS = {
        "RTX_4090",
        "RTX_4080",
        "RTX_4080_Super",
        "RTX_4070_Ti",
        "RTX_4070_Ti_Super",
        "H100",
        "H100_PCIe",
        "L40S",
        "L40",
    }
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv('VASTAI_API_KEY')
        if not self.api_key:
            raise ValueError("VASTAI_API_KEY not found in environment or config/.env")
        
        self.headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }
        
        # Configuration from environment
        self.gpu_type = os.getenv('VASTAI_GPU_TYPE', 'RTX_4090')
        self.num_gpus = int(os.getenv('VASTAI_NUM_GPUS', '2'))
        self.min_vram = int(os.getenv('VASTAI_MIN_VRAM', '24'))
        self.max_price = float(os.getenv('VASTAI_MAX_PRICE', '1.00'))
        self.disk_size = int(os.getenv('VASTAI_DISK_SIZE', '50'))
        self.blocked_instance_ids_path = Path("logs/blocked_instance_ids.json")
        self.blocked_host_ids_path = Path("logs/blocked_host_ids.json")
        self.blocked_offer_ids_path = Path("logs/blocked_offer_ids.json")
        
        logger.info(f"Vast.ai Manager initialized")
        logger.info(f"Target: {self.num_gpus}x {self.gpu_type}, Max price: ${self.max_price}/hr")

    def _ensure_logs_dir(self) -> None:
        self.blocked_instance_ids_path.parent.mkdir(parents=True, exist_ok=True)

    def _load_blocked_ids(self, path: Path) -> set:
        if not path.exists():
            return set()
        try:
            with path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, list):
                return {int(value) for value in data}
            logger.warning("Blocked IDs file %s is malformed; resetting.", path)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            logger.warning("Failed to read blocked IDs from %s: %s", path, exc)
        return set()

    def _save_blocked_ids(self, path: Path, ids: set) -> None:
        self._ensure_logs_dir()
        with path.open("w", encoding="utf-8") as handle:
            json.dump(sorted(ids), handle, indent=2)

    def get_blocked_instance_ids(self) -> set:
        return self._load_blocked_ids(self.blocked_instance_ids_path)

    def get_blocked_host_ids(self) -> set:
        return self._load_blocked_ids(self.blocked_host_ids_path)

    def get_blocked_offer_ids(self) -> set:
        return self._load_blocked_ids(self.blocked_offer_ids_path)

    def block_instance(self, instance_id: int, status_data: Optional[Dict] = None, reason: str = "unknown") -> None:
        blocked_ids = self.get_blocked_instance_ids()
        if instance_id in blocked_ids:
            return
        blocked_ids.add(int(instance_id))
        self._save_blocked_ids(self.blocked_instance_ids_path, blocked_ids)
        logger.warning(
            "Blocked instance %s due to %s at %s.",
            instance_id,
            reason,
            datetime.utcnow().isoformat(timespec="seconds"),
        )

        status = status_data
        if status is None:
            response = self.get_instance_status(instance_id)
            status = response.get("instances", {}) if response else {}

        host_id = status.get("host_id")
        if host_id:
            self.block_host(host_id, reason=reason, instance_id=instance_id)

        offer_id = status.get("bundle_id") or status.get("offer_id")
        if offer_id:
            self.block_offer(offer_id, reason=reason, instance_id=instance_id)

    def block_host(self, host_id: int, reason: str = "unknown", instance_id: Optional[int] = None) -> None:
        blocked_hosts = self.get_blocked_host_ids()
        if host_id in blocked_hosts:
            return
        blocked_hosts.add(int(host_id))
        self._save_blocked_ids(self.blocked_host_ids_path, blocked_hosts)
        logger.warning(
            "Blocked host %s due to %s (instance %s).",
            host_id,
            reason,
            instance_id if instance_id is not None else "n/a",
        )

    def block_offer(self, offer_id: int, reason: str = "unknown", instance_id: Optional[int] = None) -> None:
        blocked_offers = self.get_blocked_offer_ids()
        if offer_id in blocked_offers:
            return
        blocked_offers.add(int(offer_id))
        self._save_blocked_ids(self.blocked_offer_ids_path, blocked_offers)
        logger.warning(
            "Blocked offer %s due to %s (instance %s).",
            offer_id,
            reason,
            instance_id if instance_id is not None else "n/a",
        )
    
    def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Dict:
        """Make authenticated request to Vast.ai API"""
        url = f"{self.BASE_URL}{endpoint}?api_key={self.api_key}"
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=self.headers, timeout=30)
            elif method == 'POST':
                response = requests.post(url, headers=self.headers, json=data, timeout=30)
            elif method == 'PUT':
                response = requests.put(url, headers=self.headers, json=data, timeout=30)
            elif method == 'DELETE':
                response = requests.delete(url, headers=self.headers, timeout=30)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            response.raise_for_status()
            return response.json()
        
        except requests.RequestException as e:
            logger.error(f"API request failed: {e}")
            if hasattr(e, 'response') and hasattr(e.response, 'text'):
                logger.error(f"Response: {e.response.text}")
            raise
    
    def search_offers(
        self,
        limit: int = 10,
        exclude_offer_ids: Optional[set] = None,
        exclude_host_ids: Optional[set] = None,
    ) -> List[VastInstance]:
        """
        Search for available GPU instances
        
        Returns:
            List of VastInstance objects sorted by price
        """
        logger.info(f"Searching for {self.num_gpus}x {self.gpu_type} instances...")

        quantization = os.getenv('MLNODE_QUANTIZATION', '').lower()
        if quantization == 'auto' and self.gpu_type != 'ANY':
            if self.gpu_type not in self.FP8_CAPABLE_GPUS:
                logger.warning(
                    "⚠️  GPU type '%s' may not support FP8 quantization. "
                    "Recommended GPUs: %s",
                    self.gpu_type,
                    ", ".join(sorted(self.FP8_CAPABLE_GPUS)),
                )
        
        try:
            # Build search query
            query = {
                'verified': {'eq': True},
                'external': {'eq': False},
                'rentable': {'eq': True},
                'num_gpus': {'eq': self.num_gpus},
                'gpu_ram': {'gte': self.min_vram},
                'dph_total': {'lte': self.max_price},
                'disk_space': {'gte': self.disk_size}
            }
            
            # Add GPU name filter if specified
            if self.gpu_type != 'ANY':
                query['gpu_name'] = {'eq': self.gpu_type}
            
            response = self._make_request('POST', '/bundles/', data=query)
            
            if not response.get('offers'):
                logger.warning("No offers found matching criteria")
                return []
            
            excluded_offers = set(exclude_offer_ids or [])
            excluded_hosts = set(exclude_host_ids or [])

            # Parse and sort offers
            instances = []
            for offer in response['offers'][:limit]:
                if excluded_offers and offer['id'] in excluded_offers:
                    continue
                if excluded_hosts and offer.get('host_id') in excluded_hosts:
                    continue
                if quantization == 'auto':
                    gpu_name_normalized = offer['gpu_name'].replace(' ', '_').replace('-', '_')
                    if gpu_name_normalized not in self.FP8_CAPABLE_GPUS:
                        logger.debug("Skipping %s - not FP8 capable", offer['gpu_name'])
                        continue
                instance = VastInstance(
                    id=offer['id'],
                    status=offer.get('machine_status', 'unknown'),
                    gpu_name=offer['gpu_name'],
                    num_gpus=offer['num_gpus'],
                    gpu_ram=offer['gpu_ram'],
                    dph_total=offer['dph_total'],
                    inet_up=offer.get('inet_up', 0),
                    inet_down=offer.get('inet_down', 0),
                    host_id=offer['host_id']
                )
                instances.append(instance)
            
            # Sort by price
            instances.sort(key=lambda x: x.dph_total)
            
            logger.info(f"Found {len(instances)} available instances")
            return instances
        
        except Exception as e:
            logger.error(f"Failed to search offers: {e}")
            return []
    
    def create_instance(
        self,
        offer_id: int,
        image: Optional[str] = None,
        disk: int = 50,
        onstart: Optional[str] = None
    ) -> Optional[int]:
        """
        Create (rent) a GPU instance
        
        Args:
            offer_id: ID of the offer to rent
            image: Docker image to use
            disk: Disk size in GB
            onstart: Startup script (optional)
        
        Returns:
            Instance ID if successful, None otherwise
        """
        logger.info(f"Creating instance from offer {offer_id}...")
        
        try:
            resolved_image = image or os.getenv(
                "DOCKER_IMAGE",
                os.getenv("VASTAI_DOCKER_IMAGE", "vllm/vllm-openai:latest"),
            )
            data = {
                'client_id': 'me',
                'image': resolved_image,
                'disk': disk,
                'label': 'gonka-poc-sprint'
            }
            
            if onstart:
                data['onstart'] = onstart
            
            logger.info("Using image: %s", resolved_image)
            response = self._make_request('PUT', f'/asks/{offer_id}/', data=data)
            
            if response.get('success'):
                instance_id = response.get('new_contract')
                logger.info(f"✅ Instance created: {instance_id}")
                return instance_id
            else:
                logger.error(f"Failed to create instance: {response}")
                return None
        
        except Exception as e:
            logger.error(f"Error creating instance: {e}")
            return None
    
    def get_instance_status(self, instance_id: int) -> Optional[Dict]:
        """Get status of a specific instance"""
        try:
            response = self._make_request('GET', f'/instances/{instance_id}/')
            return response
        except Exception as e:
            logger.error(f"Failed to get instance status: {e}")
            return None
    
    def start_instance(self, instance_id: int) -> bool:
        """Start a stopped instance"""
        logger.info(f"Starting instance {instance_id}...")
        try:
            response = self._make_request('PUT', f'/instances/{instance_id}/start/')
            success = response.get('success', False)
            if success:
                logger.info(f"✅ Instance {instance_id} started")
            return success
        except Exception as e:
            logger.error(f"Failed to start instance: {e}")
            return False
    
    def stop_instance(self, instance_id: int) -> bool:
        """Stop a running instance"""
        logger.info(f"Stopping instance {instance_id}...")
        try:
            response = self._make_request('PUT', f'/instances/{instance_id}/stop/')
            success = response.get('success', False)
            if success:
                logger.info(f"✅ Instance {instance_id} stopped")
            return success
        except Exception as e:
            logger.error(f"Failed to stop instance: {e}")
            return False
    
    def destroy_instance(self, instance_id: int) -> bool:
        """Destroy (delete) an instance"""
        logger.info(f"Destroying instance {instance_id}...")
        try:
            response = self._make_request('DELETE', f'/instances/{instance_id}/')
            success = response.get('success', False)
            if success:
                logger.info(f"✅ Instance {instance_id} destroyed")
            return success
        except Exception as e:
            logger.error(f"Failed to destroy instance: {e}")
            return False
    
    def wait_for_ready(self, instance_id: int, timeout: int = 600) -> bool:
        """
        Wait for instance to be ready
        
        Args:
            instance_id: Instance to wait for
            timeout: Maximum time to wait in seconds (default 10 minutes for large Docker images)
        
        Returns:
            True if instance is ready, False if timeout
        """
        logger.info(f"Waiting for instance {instance_id} to be ready (timeout: {timeout}s)...")
        start_time = time.time()
        check_count = 0
        actual_status = 'unknown'
        last_status = {}
        
        while time.time() - start_time < timeout:
            check_count += 1
            
            # Add delay between API calls to avoid rate limiting
            if check_count > 1:
                time.sleep(2)  # 2 second delay between checks
            
            response = self.get_instance_status(instance_id)
            
            if not response:
                logger.warning(f"Check #{check_count}: No status response, retrying...")
                time.sleep(10)
                continue
            
            # The API wraps instance data in an "instances" key
            status = response.get('instances', {})
            
            if not status:
                logger.warning(f"Check #{check_count}: Empty instances data, retrying...")
                time.sleep(10)
                continue

            last_status = status
            
            # DEBUG: Print response structure (first 3 checks and every 10th)
            if check_count <= 3 or check_count % 10 == 0:
                logger.info(f"🔍 Check #{check_count} - Status Fields: {list(status.keys())[:15]}")
                logger.info(f"🔍 Check #{check_count} - cur_state={status.get('cur_state')}, actual_status={status.get('actual_status')}")
            
            # Try multiple possible status fields - cur_state is the primary one
            actual_status = (
                status.get('cur_state') or 
                status.get('actual_status') or 
                status.get('status_msg') or 
                status.get('state') or 
                status.get('status') or 
                status.get('container_status') or
                status.get('machine_status') or
                status.get('running') or
                'unknown'
            )
            
            if actual_status:
                actual_status = str(actual_status).lower().strip()
            else:
                actual_status = 'unknown'
            
            elapsed = int(time.time() - start_time)
            logger.info(f"Check #{check_count} ({elapsed}s): Instance status = {actual_status}")
            
            status_msg = str(status.get('status_msg', '')).lower()
            if any(token in status_msg for token in ['download', 'pull', 'extract', 'image']):
                logger.info(
                    f"Instance {instance_id} is still downloading the image: {status_msg or 'waiting'}"
                )
                time.sleep(10)
                continue

            ssh_host = status.get('ssh_host')
            ssh_port = status.get('ssh_port')

            # Check for ready states (multiple variations) and SSH availability
            if actual_status in ['running', 'active', 'ready', 'started', 'success', 'true', '1']:
                if ssh_host and ssh_port:
                    logger.info(f"✅ Instance {instance_id} is ready and SSH is available!")
                    return True
                logger.info("Instance reported ready but SSH details are missing, waiting...")
            
            # Check for failure states
            if actual_status in ['failed', 'exited', 'error', 'terminated', 'destroyed', 'false', '0']:
                logger.error(f"❌ Instance {instance_id} failed with status: {actual_status}")
                self.block_instance(instance_id, status_data=last_status, reason=f"status:{actual_status}")
                return False
            
            # Still waiting...
            time.sleep(10)
        
        # Timeout reached
        logger.error(f"❌ Timeout waiting for instance {instance_id} after {timeout}s")
        logger.error(f"Last status was: {actual_status}")
        self.block_instance(instance_id, status_data=last_status, reason="ready-timeout")
        return False
    
    def get_instance_cost(self, instance_id: int) -> Optional[float]:
        """Get total cost accumulated for an instance"""
        try:
            response = self.get_instance_status(instance_id)
            if response:
                instances_data = response.get('instances', {})
                return instances_data.get('total_cost', 0.0)
            return None
        except Exception:
            return None
    
    def list_my_instances(self) -> List[Dict]:
        """List all instances owned by the user"""
        try:
            response = self._make_request('GET', '/instances/')
            return response.get('instances', [])
        except Exception as e:
            logger.error(f"Failed to list instances: {e}")
            return []


def test_connection():
    """Test Vast.ai API connection"""
    print("\n" + "="*60)
    print("  TEST: Vast.ai API Connection")
    print("="*60 + "\n")
    
    try:
        manager = VastAIManager()
        
        # Test: List current instances
        instances = manager.list_my_instances()
        print(f"✅ Connected to Vast.ai API")
        print(f"Current instances: {len(instances)}")
        
        if instances:
            for inst in instances:
                status = inst.get('cur_state', inst.get('actual_status', inst.get('status', 'unknown')))
                print(f"  - Instance {inst['id']}: {status}")
        
        return True
    
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False


def test_search():
    """Test searching for GPU offers"""
    print("\n" + "="*60)
    print("  TEST: Search for 2x RTX 4090")
    print("="*60 + "\n")
    
    try:
        manager = VastAIManager()
        offers = manager.search_offers(limit=5)
        
        if offers:
            print(f"✅ Found {len(offers)} offers:\n")
            for i, offer in enumerate(offers, 1):
                print(f"{i}. {offer}")
                print(f"   Upload: {offer.inet_up:.0f} Mbps, Download: {offer.inet_down:.0f} Mbps")
                print()
            return True
        else:
            print("❌ No offers found matching criteria")
            print("\nTry adjusting config/.env:")
            print("  - VASTAI_MAX_PRICE (increase if needed)")
            print("  - VASTAI_GPU_TYPE (try 'ANY' to see all options)")
            return False
    
    except Exception as e:
        print(f"❌ Search failed: {e}")
        return False


if __name__ == "__main__":
    print("\n" + "="*60)
    print("  Vast.ai Manager - Test Suite")
    print("="*60)
    
    # Test 1: Connection
    if not test_connection():
        print("\n⚠️  Fix your API key in config/.env and try again")
        exit(1)
    
    # Test 2: Search
    test_search()
    
    print("\n" + "="*60)
    print("  Tests Complete!")
    print("="*60)
    print("\n✅ Vast.ai Manager is ready!")
