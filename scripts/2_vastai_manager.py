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
from dotenv import load_dotenv

load_dotenv('config/.env')

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
        self.num_gpus = 2  # We need 2 GPUs for PoC
        self.min_vram = int(os.getenv('VASTAI_MIN_VRAM', '24'))
        self.max_price = float(os.getenv('VASTAI_MAX_PRICE', '1.00'))
        self.disk_size = int(os.getenv('VASTAI_DISK_SIZE', '50'))
        
        logger.info(f"Vast.ai Manager initialized")
        logger.info(f"Target: {self.num_gpus}x {self.gpu_type}, Max price: ${self.max_price}/hr")
    
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
            if hasattr(e.response, 'text'):
                logger.error(f"Response: {e.response.text}")
            raise
    
    def search_offers(self, limit: int = 10) -> List[VastInstance]:
        """
        Search for available GPU instances
        
        Returns:
            List of VastInstance objects sorted by price
        """
        logger.info(f"Searching for {self.num_gpus}x {self.gpu_type} instances...")
        
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
            
            # Parse and sort offers
            instances = []
            for offer in response['offers'][:limit]:
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
        image: str = "nvidia/cuda:12.1.0-base-ubuntu22.04",
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
            data = {
                'client_id': 'me',
                'image': image,
                'disk': disk,
                'label': 'gonka-poc-sprint'
            }
            
            if onstart:
                data['onstart'] = onstart
            
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
    
    def wait_for_ready(self, instance_id: int, timeout: int = 300) -> bool:
        """
        Wait for instance to be ready
        
        Args:
            instance_id: Instance to wait for
            timeout: Maximum time to wait in seconds
        
        Returns:
            True if instance is ready, False if timeout
        """
        logger.info(f"Waiting for instance {instance_id} to be ready...")
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            status = self.get_instance_status(instance_id)
            
            if not status:
                time.sleep(10)
                continue
            
            actual_status = status.get('actual_status') or status.get('status_msg') or status.get('state', 'unknown')
            logger.info(f"Instance status: {actual_status}")
            
            if actual_status == 'running':
                logger.info(f"✅ Instance {instance_id} is ready!")
                return True
            
            if actual_status in ['failed', 'exited']:
                logger.error(f"❌ Instance {instance_id} failed to start")
                return False
            
            time.sleep(10)
        
        logger.error(f"❌ Timeout waiting for instance {instance_id}")
        return False
    
    def get_instance_cost(self, instance_id: int) -> Optional[float]:
        """Get total cost accumulated for an instance"""
        try:
            status = self.get_instance_status(instance_id)
            if status:
                return status.get('total_cost', 0.0)
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
                print(f"  - Instance {inst['id']}: {inst.get('actual_status', 'unknown')}")
        
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
    print("Next: I'll build Script 3 (PoC Scheduler)")
# [Copy the entire script from the artifact above]
