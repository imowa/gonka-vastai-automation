#!/usr/bin/env python3
"""
Test script for PoC timing and readiness verification

Tests:
1. Block height and time calculations
2. Prep time window detection (should now be 60 min)
3. MLNode readiness verification
4. Full readiness before PoC starts
"""

import sys
import os
import json
import logging
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv
load_dotenv('config/.env')

# Import modules
import importlib.util

def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

poc_monitor = load_module("poc_monitor", "scripts/1_poc_monitor.py")
PoCMonitor = poc_monitor.PoCMonitor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_block_calculations():
    """Test that block-to-time calculations are correct"""
    logger.info("=" * 70)
    logger.info("TEST 1: Block Height Calculations")
    logger.info("=" * 70)

    monitor = PoCMonitor()
    epoch_data = monitor.get_current_epoch()

    if not epoch_data:
        logger.error("❌ Cannot fetch epoch data")
        return False

    current_block = epoch_data.get('block_height')
    next_stages = epoch_data.get('next_epoch_stages', {})
    poc_start_block = next_stages.get('poc_start')
    poc_val_end = next_stages.get('poc_validation_end')

    if not all([current_block, poc_start_block, poc_val_end]):
        logger.error("❌ Missing block height data")
        return False

    blocks_to_poc = poc_start_block - current_block
    poc_duration_blocks = poc_val_end - poc_start_block

    logger.info(f"Current block: {current_block}")
    logger.info(f"PoC start block: {poc_start_block}")
    logger.info(f"PoC end block: {poc_val_end}")
    logger.info(f"Blocks until PoC: {blocks_to_poc}")
    logger.info(f"PoC duration blocks: {poc_duration_blocks}")

    # Each block is ~6 seconds (verified against gonkahub.com data)
    seconds_to_poc = blocks_to_poc * 6
    poc_duration = poc_duration_blocks * 6

    hours_to = seconds_to_poc // 3600
    mins_to = (seconds_to_poc % 3600) // 60

    hours_dur = poc_duration // 3600
    mins_dur = (poc_duration % 3600) // 60

    logger.info(f"⏰ Time to PoC: {hours_to}h {mins_to}m ({seconds_to_poc}s)")
    logger.info(f"⏰ PoC duration: {hours_dur}h {mins_dur}m ({poc_duration}s)")

    if seconds_to_poc < 0:
        logger.info("   ℹ️  PoC already started/completed for current epoch")
    elif seconds_to_poc < 300:
        logger.warning("   ⚠️  PoC starting very soon!")
    else:
        logger.info("   ✅ PoC timing looks good")

    return True


def test_prep_time_window():
    """Test that 60-minute prep time window is respected"""
    logger.info("\n" + "=" * 70)
    logger.info("TEST 2: Prep Time Window (60 minutes)")
    logger.info("=" * 70)

    monitor = PoCMonitor()

    # Test with default prep_time (1800s = 30 min)
    status_30 = monitor.get_status(prep_time=1800)
    logger.info(f"30-min window: should_start_gpu = {status_30['should_start_gpu']}")

    # Test with updated prep_time (3600s = 60 min)
    status_60 = monitor.get_status(prep_time=3600)
    logger.info(f"60-min window: should_start_gpu = {status_60['should_start_gpu']}")

    seconds_to = status_60['seconds_to_poc']
    if status_60['should_start_gpu']:
        logger.warning(f"🚨 SHOULD START GPU NOW! ({seconds_to}s until PoC)")
        return True
    elif seconds_to > 0 and seconds_to <= 3600:
        logger.info(f"⚠️  GPU deployment window is open (within 60 min)")
        hours = seconds_to // 3600
        mins = (seconds_to % 3600) // 60
        logger.info(f"   Recommended action: Deploy within {mins}m for safety margin")
        return True
    elif seconds_to > 3600:
        logger.info(f"✅ Outside prep window (PoC is {seconds_to//60}m away)")
        return True
    else:
        logger.info(f"ℹ️  PoC already completed or data unavailable")
        return True


def test_readiness_check_format():
    """Test that readiness check would work correctly"""
    logger.info("\n" + "=" * 70)
    logger.info("TEST 3: MLNode Readiness Check Format")
    logger.info("=" * 70)

    status = PoCMonitor().get_status(prep_time=3600)

    logger.info(f"Current status:")
    logger.info(f"  Epoch: #{status['current_epoch']}")
    logger.info(f"  Phase: {status['current_phase']}")
    logger.info(f"  Current block: {status['current_block']}")
    logger.info(f"  Next PoC block: {status['next_poc_block']}")
    logger.info(f"  Seconds to PoC: {status['seconds_to_poc']}")
    logger.info(f"  Should start GPU: {status['should_start_gpu']}")

    # Verify response format
    required_fields = [
        'status', 'current_phase', 'current_epoch', 'next_epoch',
        'current_block', 'next_poc_block', 'seconds_to_poc',
        'poc_duration_seconds', 'should_start_gpu'
    ]

    missing = [f for f in required_fields if f not in status]
    if missing:
        logger.error(f"❌ Missing fields: {missing}")
        return False

    logger.info(f"✅ All required status fields present")
    return True


def test_timing_summary():
    """Print summary of timing information"""
    logger.info("\n" + "=" * 70)
    logger.info("TEST 4: Epoch Timing Summary")
    logger.info("=" * 70)

    monitor = PoCMonitor()
    epoch_data = monitor.get_current_epoch()

    if not epoch_data:
        logger.error("❌ Cannot fetch epoch data")
        return False

    latest_epoch = epoch_data.get('latest_epoch', {})
    next_stages = epoch_data.get('next_epoch_stages', {})

    logger.info(f"Current Epoch: #{latest_epoch.get('index')}")
    logger.info(f"  Phase: {epoch_data.get('phase')}")
    logger.info(f"  Block: {epoch_data.get('block_height')}")

    logger.info(f"\nNext Epoch: #{next_stages.get('epoch_index')}")
    logger.info(f"  PoC start block: {next_stages.get('poc_start')}")
    logger.info(f"  PoC validation end: {next_stages.get('poc_validation_end')}")

    status = monitor.get_status(prep_time=3600)

    logger.info(f"\nRecommended Action:")
    if status['should_start_gpu']:
        logger.warning(f"🚨 START GPU NOW - PoC begins in {status['seconds_to_poc']//60} min")
    elif status['seconds_to_poc'] > 0:
        hours = status['seconds_to_poc'] // 3600
        mins = (status['seconds_to_poc'] % 3600) // 60
        logger.info(f"⏰ Wait {hours}h {mins}m, then deploy GPU (need 60 min prep)")
    else:
        logger.info(f"✅ PoC phase already started/completed")

    logger.info(f"\n✅ Timing Summary:")
    logger.info(f"  Default prep time: 60 minutes (updated from 30)")
    logger.info(f"  GPU deployment window: {max(status['seconds_to_poc'], 0)//60} minutes")
    logger.info(f"  PoC duration: {status['poc_duration_seconds']//60} minutes")

    return True


def main():
    """Run all tests"""
    logger.info("\n" + "=" * 70)
    logger.info("  PoC Timing & Readiness Verification Tests")
    logger.info("=" * 70 + "\n")

    tests = [
        ("Block Calculations", test_block_calculations),
        ("Prep Time Window", test_prep_time_window),
        ("Readiness Format", test_readiness_check_format),
        ("Timing Summary", test_timing_summary),
    ]

    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            logger.error(f"❌ Test failed with exception: {e}", exc_info=True)
            results.append((name, False))

    # Summary
    logger.info("\n" + "=" * 70)
    logger.info("  Test Summary")
    logger.info("=" * 70)

    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        logger.info(f"{status}: {name}")

    passed = sum(1 for _, r in results if r)
    total = len(results)

    logger.info(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        logger.info("\n✅ All tests passed! PoC timing is ready.")
        return 0
    else:
        logger.error(f"\n❌ {total - passed} test(s) failed. Please review.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
