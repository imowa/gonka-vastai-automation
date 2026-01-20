#!/usr/bin/env python3
"""
Manual PoC Sprint Starter
Starts a GPU instance and participates in the current running PoC epoch.

Use this when:
- PoC has already started and you want to join mid-epoch
- Testing PoC functionality
- Scheduler missed the start window

Usage:
    python3 manual_poc_start.py
    python3 manual_poc_start.py --epoch 145
"""

import sys
import os
import argparse
import logging
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

load_dotenv('config/.env')

# Import using correct module names
import importlib.util

# Load PoC Scheduler
spec = importlib.util.spec_from_file_location("poc_scheduler", "scripts/3_poc_scheduler.py")
scheduler_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scheduler_module)
PoCScheduler = scheduler_module.PoCScheduler

# Load PoC Monitor
spec = importlib.util.spec_from_file_location("poc_monitor", "scripts/1_poc_monitor.py")
monitor_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(monitor_module)
PoCMonitor = monitor_module.PoCMonitor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_current_epoch() -> int:
    """Get current epoch from blockchain"""
    monitor = PoCMonitor()
    status = monitor.get_status()

    if status['status'] != 'active':
        logger.error("Cannot fetch blockchain data")
        return None

    return status['current_epoch']


def main():
    parser = argparse.ArgumentParser(description='Manually start PoC participation')
    parser.add_argument(
        '--epoch',
        type=int,
        help='Epoch number to participate in (default: current epoch)'
    )
    parser.add_argument(
        '--skip-poc-wait',
        action='store_true',
        help='Skip waiting for PoC completion (just deploy and exit)'
    )

    args = parser.parse_args()

    # Get epoch number
    if args.epoch:
        epoch = args.epoch
        logger.info(f"Using specified epoch: {epoch}")
    else:
        logger.info("Fetching current epoch from blockchain...")
        epoch = get_current_epoch()
        if not epoch:
            logger.error("Failed to get current epoch")
            sys.exit(1)
        logger.info(f"Current epoch: {epoch}")

    # Initialize scheduler
    logger.info("Initializing PoC Scheduler...")
    scheduler = PoCScheduler()

    # Show current status
    logger.info("")
    logger.info("="*70)
    logger.info("  Manual PoC Sprint Start")
    logger.info("="*70)
    logger.info(f"  Epoch: {epoch}")
    logger.info(f"  Max daily spend: ${scheduler.max_daily_spend}")
    logger.info(f"  Current daily spend: ${scheduler.daily_spend:.2f}")
    logger.info("="*70)
    logger.info("")

    # Confirm
    response = input("Start GPU instance for PoC participation? (yes/no): ")
    if response.lower() not in ['yes', 'y']:
        logger.info("Cancelled by user")
        sys.exit(0)

    # Execute PoC cycle
    logger.info("")
    logger.info("🚀 Starting PoC Sprint...")
    logger.info("")

    try:
        if args.skip_poc_wait:
            # Just create instance and deploy MLNode, don't wait
            logger.info("Note: Will deploy MLNode but not wait for PoC completion")

            # Create GPU instance
            instance_id = scheduler.start_gpu_instance_with_retries()
            if instance_id:
                logger.info(f"✅ GPU instance created: {instance_id}")

                # Deploy MLNode
                from scripts.mlnode_poc_manager import MLNodePoCManager
                mlnode_manager = MLNodePoCManager()

                success = scheduler.run_poc_sprint(instance_id)
                if success:
                    logger.info(f"✅ MLNode deployed successfully")
                    logger.info(f"   Instance ID: {instance_id}")
                    logger.info(f"   Instance will remain running for PoC tasks")
                else:
                    logger.error("Failed to deploy MLNode")
                    scheduler.stop_gpu_instance(instance_id)
                    sys.exit(1)
            else:
                logger.error("Failed to create GPU instance")
                sys.exit(1)
        else:
            # Full PoC cycle with monitoring
            scheduler.execute_poc_cycle(epoch)

        logger.info("")
        logger.info("="*70)
        logger.info("  PoC Sprint Complete")
        logger.info("="*70)
        logger.info(f"  Total cost: ${scheduler.current_session.total_cost:.3f}" if scheduler.current_session else "  No cost data")
        logger.info(f"  Daily spend: ${scheduler.daily_spend:.2f} / ${scheduler.max_daily_spend}")
        logger.info("="*70)

    except KeyboardInterrupt:
        logger.info("\n⚠️  Interrupted by user")
        if scheduler.current_session and scheduler.current_session.instance_id:
            response = input("Stop and destroy GPU instance? (yes/no): ")
            if response.lower() in ['yes', 'y']:
                scheduler.stop_gpu_instance(scheduler.current_session.instance_id)
        sys.exit(0)

    except Exception as e:
        logger.error(f"Error during PoC sprint: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
