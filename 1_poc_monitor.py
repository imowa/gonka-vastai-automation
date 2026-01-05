#!/usr/bin/env python3
"""
PoC Sprint Monitor
Monitors Gonka blockchain to detect when PoC Sprint is about to start.
"""

import requests
import time
import json
from datetime import datetime, timedelta
from typing import Optional, Dict
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PoCMonitor:
    """Monitor Gonka blockchain for PoC Sprint timing"""
    
    def __init__(
        self,
        node_url: str = "http://node2.gonka.ai:8000",
        check_interval: int = 300  # Check every 5 minutes
    ):
        self.node_url = node_url
        self.check_interval = check_interval
        self.last_epoch = None
        
    def get_current_epoch(self) -> Optional[Dict]:
        """Fetch current epoch information from Gonka node"""
        try:
            url = f"{self.node_url}/v1/epochs/current"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to fetch epoch data: {e}")
            return None
    
    def get_epoch_participants(self) -> Optional[Dict]:
        """Fetch current PoC participants"""
        try:
            url = f"{self.node_url}/v1/epochs/current/participants"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to fetch participants: {e}")
            return None
    
    def calculate_time_to_poc(self, epoch_data: Dict) -> Optional[int]:
        """
        Calculate seconds until next PoC Sprint
        
        Returns:
            seconds until PoC Sprint, or None if cannot calculate
        """
        try:
            # Parse epoch timing (adjust based on actual API response)
            # This is a placeholder - you'll need to adjust based on actual data
            current_time = time.time()
            
            if 'epoch_end' in epoch_data:
                epoch_end = epoch_data['epoch_end']
                seconds_remaining = epoch_end - current_time
                return max(0, int(seconds_remaining))
            
            # If epoch_end not available, estimate from epoch start + 24h
            if 'epoch_start' in epoch_data:
                epoch_start = epoch_data['epoch_start']
                epoch_duration = 24 * 3600  # 24 hours
                next_poc = epoch_start + epoch_duration
                seconds_remaining = next_poc - current_time
                return max(0, int(seconds_remaining))
            
            return None
            
        except (KeyError, TypeError, ValueError) as e:
            logger.error(f"Error calculating PoC time: {e}")
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
    
    def monitor_loop(self, callback_on_poc_alert=None):
        """
        Main monitoring loop
        
        Args:
            callback_on_poc_alert: Function to call when PoC Sprint is approaching
        """
        logger.info("Starting PoC monitoring...")
        logger.info(f"Checking every {self.check_interval} seconds")
        
        while True:
            try:
                # Fetch current epoch
                epoch_data = self.get_current_epoch()
                
                if epoch_data:
                    logger.info(f"Epoch data: {json.dumps(epoch_data, indent=2)}")
                    
                    # Calculate time to PoC
                    seconds_to_poc = self.calculate_time_to_poc(epoch_data)
                    
                    if seconds_to_poc is not None:
                        hours = seconds_to_poc // 3600
                        minutes = (seconds_to_poc % 3600) // 60
                        logger.info(f"Time to next PoC Sprint: {hours}h {minutes}m")
                        
                        # Check if we should alert
                        if self.should_start_gpu(seconds_to_poc):
                            logger.warning(f"⚠️  PoC Sprint in {minutes} minutes! Time to start GPU!")
                            
                            if callback_on_poc_alert:
                                callback_on_poc_alert(seconds_to_poc)
                        
                        # Check if new epoch started
                        current_epoch_id = epoch_data.get('epoch_id')
                        if self.last_epoch and current_epoch_id != self.last_epoch:
                            logger.info(f"🔄 New epoch detected: {current_epoch_id}")
                        
                        self.last_epoch = current_epoch_id
                    else:
                        logger.warning("Could not calculate time to PoC")
                else:
                    logger.error("No epoch data received")
                
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}", exc_info=True)
            
            # Wait before next check
            time.sleep(self.check_interval)
    
    def get_status(self) -> Dict:
        """Get current monitoring status"""
        epoch_data = self.get_current_epoch()
        
        if not epoch_data:
            return {"status": "error", "message": "Cannot fetch epoch data"}
        
        seconds_to_poc = self.calculate_time_to_poc(epoch_data)
        
        return {
            "status": "active",
            "current_epoch": epoch_data.get('epoch_id'),
            "seconds_to_poc": seconds_to_poc,
            "should_start_gpu": self.should_start_gpu(seconds_to_poc) if seconds_to_poc else False,
            "last_check": datetime.now().isoformat()
        }


def example_callback(seconds_remaining: int):
    """Example callback when PoC Sprint is approaching"""
    print(f"\n{'='*50}")
    print(f"🚨 ALERT: PoC Sprint starting in {seconds_remaining} seconds!")
    print(f"{'='*50}\n")
    # Here you would trigger GPU startup


if __name__ == "__main__":
    # Example usage
    monitor = PoCMonitor(
        node_url="http://node2.gonka.ai:8000",
        check_interval=300  # Check every 5 minutes
    )
    
    # Test single check
    print("Testing epoch fetch...")
    status = monitor.get_status()
    print(f"Status: {json.dumps(status, indent=2)}")
    
    # Uncomment to run continuous monitoring
    # monitor.monitor_loop(callback_on_poc_alert=example_callback)
