#!/usr/bin/env python3
"""
PoC Sprint Monitor
Monitors Gonka blockchain to detect when PoC Sprint is about to start.
"""

import requests
import time
import json
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict
import logging

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


class PoCMonitor:
    """Monitor Gonka blockchain for PoC Sprint timing"""
    
    def __init__(
        self,
        node_url: Optional[str] = None,
        check_interval: int = 300,
        request_timeout: Optional[int] = None,
        max_retries: Optional[int] = None
    ):
        self.node_url = node_url or os.getenv('GONKA_NETWORK_NODE_URL', "http://node2.gonka.ai:8000")
        self.check_interval = check_interval
        self.request_timeout = request_timeout or int(os.getenv('GONKA_API_TIMEOUT', '10'))
        self.max_retries = max_retries or int(os.getenv('GONKA_API_RETRIES', '3'))
        self.last_epoch = None
        
    def get_current_epoch(self) -> Optional[Dict]:
        """Fetch current epoch information from Gonka node"""
        url = f"{self.node_url}/api/v1/epochs/latest"
        for attempt in range(1, self.max_retries + 1):
            try:
                response = requests.get(url, timeout=self.request_timeout)
                response.raise_for_status()
                return response.json()
            except requests.RequestException as e:
                if attempt < self.max_retries:
                    backoff = min(2 ** (attempt - 1), 8)
                    logger.warning(
                        "Failed to fetch epoch data (attempt %s/%s): %s. Retrying in %ss",
                        attempt,
                        self.max_retries,
                        e,
                        backoff,
                    )
                    time.sleep(backoff)
                else:
                    logger.error(f"Failed to fetch epoch data: {e}")
        return None
    
    def calculate_time_to_poc(self, epoch_data: Dict) -> Optional[int]:
        """
        Calculate seconds until next PoC Sprint
        
        Returns:
            seconds until PoC Sprint, or None if cannot calculate
        """
        try:
            current_block = epoch_data.get('block_height', 0)
            next_stages = epoch_data.get('next_epoch_stages', {})
            next_poc_start = next_stages.get('poc_start', 0)
            
            blocks_remaining = next_poc_start - current_block
            
            # Each block is ~3 seconds (based on epoch length)
            seconds_remaining = blocks_remaining * 3
            
            return max(0, int(seconds_remaining))
            
        except (KeyError, TypeError, ValueError) as e:
            logger.error(f"Error calculating PoC time: {e}")
            return None
    
    def get_poc_duration(self, epoch_data: Dict) -> Optional[int]:
        """Calculate total PoC Sprint duration in seconds"""
        try:
            next_stages = epoch_data.get('next_epoch_stages', {})
            poc_start = next_stages.get('poc_start', 0)
            poc_val_end = next_stages.get('poc_validation_end', 0)
            
            blocks_duration = poc_val_end - poc_start
            seconds_duration = blocks_duration * 3
            
            return int(seconds_duration)
        except (KeyError, TypeError, ValueError):
            return None
    
    def should_start_gpu(self, seconds_to_poc: int, prep_time: int = 1800) -> bool:
        """
        Determine if it's time to start GPU
        
        Args:
            seconds_to_poc: Seconds until PoC Sprint
            prep_time: Time needed to prepare GPU (default 30 minutes)
        
        Returns:
            True if should start GPU now
        """
        return 0 < seconds_to_poc <= prep_time
    
    def get_status(self, prep_time: int = 1800) -> Dict:
        """
        Get current monitoring status

        Args:
            prep_time: Time needed to prepare GPU (seconds), default 30 min
        """
        epoch_data = self.get_current_epoch()

        if not epoch_data:
            return {"status": "error", "message": "Cannot fetch epoch data"}

        seconds_to_poc = self.calculate_time_to_poc(epoch_data)
        poc_duration = self.get_poc_duration(epoch_data)

        latest_epoch = epoch_data.get('latest_epoch', {})
        next_stages = epoch_data.get('next_epoch_stages', {})

        return {
            "status": "active",
            "current_phase": epoch_data.get('phase'),
            "current_epoch": latest_epoch.get('index'),
            "next_epoch": next_stages.get('epoch_index'),
            "current_block": epoch_data.get('block_height'),
            "next_poc_block": next_stages.get('poc_start'),
            "seconds_to_poc": seconds_to_poc,
            "poc_duration_seconds": poc_duration,
            "should_start_gpu": self.should_start_gpu(seconds_to_poc, prep_time) if seconds_to_poc else False,
            "last_check": datetime.now().isoformat()
        }


if __name__ == "__main__":
    monitor = PoCMonitor()
    print("Testing epoch fetch...")
    status = monitor.get_status()
    print(f"\nStatus: {json.dumps(status, indent=2)}")
    
    if status['seconds_to_poc']:
        hours = status['seconds_to_poc'] // 3600
        minutes = (status['seconds_to_poc'] % 3600) // 60
        print(f"\n⏰ Time to next PoC Sprint: {hours}h {minutes}m")
        
        if status['poc_duration_seconds']:
            poc_minutes = status['poc_duration_seconds'] // 60
            print(f"📊 PoC Sprint duration: ~{poc_minutes} minutes")
