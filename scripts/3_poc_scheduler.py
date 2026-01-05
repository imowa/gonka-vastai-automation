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
from datetime import datetime, timedelta
from typing import Optional, Dict
from dataclasses import dataclass
import importlib.util

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

from dotenv import load_dotenv
load_dotenv('config/.env')

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
        
        # State
        self.current_session: Optional[PoCSession] = None
        self.daily_spend = 0.0
        self.last_reset_date = datetime.now().date()
        
        logger.info("PoC Scheduler initialized")
        logger.info(f"Prep time: {self.prep_time}s ({self.prep_time//60} minutes)")
        logger.info(f"Max duration: {self.max_duration}s ({self.max_duration//3600} hours)")
        logger.info(f"Check interval: {self.check_interval}s ({self.check_interval//60} minutes)")
        logger.info(f"Max daily spend: ${self.max_daily_spend}")
    
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
    
    def select_best_gpu(self) -> Optional[int]:
        """
        Search for and select the best available GPU instance
        
        Returns:
            Offer ID if found, None otherwise
        """
        logger.info("Searching for available GPU instances...")
        
        offers = self.vastai.search_offers(limit=5)
        
        if not offers:
            logger.error("No GPU instances available")
            return None
        
        # Filter by VRAM requirement (need 40GB+ total)
        valid_offers = [o for o in offers if (o.gpu_ram * o.num_gpus) >= 40000]
        
        if not valid_offers:
            logger.error("No instances with 40GB+ VRAM found")
            logger.info("Available offers didn't meet VRAM requirements")
            return None
        
        # Select cheapest valid offer
        best_offer = valid_offers[0]
        logger.info(f"Selected: {best_offer}")
        logger.info(f"Cost estimate for 15 min: ${(best_offer.dph_total / 60) * 15:.3f}")
        
        return best_offer.id
    
    def start_gpu_instance(self, offer_id: int) -> Optional[int]:
        """
        Start a GPU instance
        
        Returns:
            Instance ID if successful, None otherwise
        """
        logger.info(f"Creating instance from offer {offer_id}...")
        
        # Docker image with Gonka MLNode
        image = os.getenv('DOCKER_IMAGE', 'nvidia/cuda:12.1.0-base-ubuntu22.04')
        disk = int(os.getenv('VASTAI_DISK_SIZE', '50'))
        
        # Startup script to prepare the instance
        onstart = """#!/bin/bash
echo "Instance started at $(date)"
nvidia-smi
echo "Ready for PoC Sprint"
"""
        
        instance_id = self.vastai.create_instance(
            offer_id=offer_id,
            image=image,
            disk=disk,
            onstart=onstart
        )
        
        if not instance_id:
            logger.error("Failed to create instance")
            return None
        
        logger.info(f"Instance {instance_id} created, waiting for ready state...")
        
        # Wait for instance to be ready
        if not self.vastai.wait_for_ready(instance_id, timeout=300):
            logger.error(f"Instance {instance_id} failed to start")
            # Try to destroy failed instance
            self.vastai.destroy_instance(instance_id)
            return None
        
        return instance_id
    
    def run_poc_sprint(self, instance_id: int) -> bool:
        """
        Run the PoC Sprint on the GPU instance
        
        This is a placeholder - in production, this would:
        1. SSH into the instance
        2. Deploy Gonka MLNode Docker
        3. Wait for PoC to complete
        4. Monitor progress
        
        Returns:
            True if successful, False otherwise
        """
        logger.info(f"Running PoC Sprint on instance {instance_id}")
        
        # TODO: Actual implementation would:
        # 1. Get instance SSH details
        # 2. Deploy Gonka MLNode
        # 3. Monitor PoC progress via API
        # 4. Wait for completion
        
        # For now, simulate PoC duration (9 minutes + buffer)
        poc_duration = 900  # 15 minutes with buffer
        logger.info(f"PoC Sprint in progress (will take ~{poc_duration//60} minutes)...")
        
        start = time.time()
        while time.time() - start < poc_duration:
            elapsed = int(time.time() - start)
            remaining = poc_duration - elapsed
            logger.info(f"PoC progress: {elapsed}s elapsed, {remaining}s remaining")
            time.sleep(60)  # Check every minute
        
        logger.info("✅ PoC Sprint completed")
        return True
    
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
            offer_id = self.select_best_gpu()
            if not offer_id:
                logger.error("Cannot start PoC: no GPU available")
                self.current_session.status = "failed"
                return
            
            # Step 3: Start GPU instance
            instance_id = self.start_gpu_instance(offer_id)
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
