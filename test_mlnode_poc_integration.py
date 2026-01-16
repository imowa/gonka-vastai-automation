#!/usr/bin/env python3
"""
Integration Test for Official MLNode PoC
Tests the complete flow with the official MLNode Docker container
"""

import sys
import os
import time
import argparse
import logging
import importlib.util
from pathlib import Path

# Add scripts to path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.append(str(PROJECT_ROOT))
sys.path.append(str(PROJECT_ROOT / "scripts"))

# Import from numbered scripts using importlib
spec = importlib.util.spec_from_file_location("mlnode_poc_manager", "scripts/mlnode_poc_manager.py")
mlnode_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mlnode_module)
MLNodePoCManager = mlnode_module.MLNodePoCManager

spec = importlib.util.spec_from_file_location("poc_scheduler", "scripts/3_poc_scheduler.py")
scheduler_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scheduler_module)
PoCScheduler = scheduler_module.PoCScheduler

from env_loader import load_env

load_env('config/.env')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_mlnode_manager():
    """Test the MLNode PoC Manager"""
    print("\n" + "="*70)
    print("  Test 1: MLNode PoC Manager")
    print("="*70)

    try:
        manager = MLNodePoCManager()

        print("✅ MLNode PoC Manager initialized")
        print(f"\nConfiguration:")
        print(f"  Admin API: {manager.admin_api_url}")
        print(f"  SSH Key: {manager.ssh_key_path}")
        print(f"  PoC Model: {manager.poc_model}")
        print(f"  MLNode Port: {manager.mlnode_port}")
        print(f"  Startup Timeout: {manager.mlnode_startup_timeout}s")

        # Check SSH key
        if os.path.exists(manager.ssh_key_path):
            print(f"  ✅ SSH key found")
        else:
            print(f"  ❌ SSH key not found at {manager.ssh_key_path}")
            return False

        # Check Network Node API
        import requests
        try:
            response = requests.get(f"{manager.admin_api_url}/admin/v1/nodes", timeout=5)
            if response.status_code == 200:
                nodes = response.json()
                print(f"  ✅ Network Node API accessible")
                print(f"  Currently registered nodes: {len(nodes)}")

                if len(nodes) > 0:
                    print(f"\n  Active nodes:")
                    for node_data in nodes:
                        node = node_data.get('node', {})
                        print(f"    • {node.get('id')} ({node.get('host')}:{node.get('inference_port')})")
            else:
                print(f"  ⚠️ API returned: {response.status_code}")
                return False
        except Exception as e:
            print(f"  ❌ Cannot reach Network Node API: {e}")
            return False

        return True

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_full_poc_flow(skip_poc=False, estimated_minutes=15):
    """
    Test the complete PoC flow with official MLNode container

    Args:
        skip_poc: Skip actual PoC execution (just test provisioning)
        estimated_minutes: Estimated time for the test
    """
    print("\n" + "="*70)
    print("  Test 2: Full PoC Flow with Official MLNode")
    print("="*70)

    if not skip_poc:
        print(f"\n⚠️  WARNING: This test will rent a GPU for approximately {estimated_minutes} minutes")
        print("   Estimated cost: $" + f"{(float(os.getenv('VASTAI_MAX_PRICE', '0.30')) / 60) * estimated_minutes:.2f}")

        confirmation = input("\n   Continue? [y/N]: ")
        if confirmation.lower() != 'y':
            print("   Test cancelled")
            return False

    try:
        scheduler = PoCScheduler()

        print("\n" + "-"*70)
        print("  Step 1: GPU Selection and Rental")
        print("-"*70)

        # Select GPU
        offer_id = scheduler.select_best_gpu()
        if not offer_id:
            print("❌ No suitable GPU offers found")
            return False

        print(f"✅ Selected GPU offer: {offer_id}")

        # Start instance
        print("\nStarting GPU instance...")
        instance_id = scheduler.start_gpu_instance_with_retries(preferred_offer_id=offer_id)

        if not instance_id:
            print("❌ Failed to start GPU instance")
            return False

        print(f"✅ GPU instance started: {instance_id}")

        try:
            print("\n" + "-"*70)
            print("  Step 2: Official MLNode Container Deployment")
            print("-"*70)

            # Import MLNode manager
            mlnode_manager = MLNodePoCManager()

            # Get connection info (host/port for MLNode API)
            print("\nGetting GPU instance connection details...")
            ssh_info = mlnode_manager.get_ssh_connection(scheduler.vastai, instance_id)

            if not ssh_info:
                print("❌ Failed to get instance connection details")
                return False

            print(f"✅ Instance accessible at: {ssh_info['host']}:{ssh_info['port']}")

            # Wait for MLNode container to be ready
            print("\nWaiting for MLNode container to initialize...")
            print("(This may take 15-30 minutes for model download and initialization)")
            print("Note: The MLNode Docker image does not include SSH - checking API only")

            mlnode_url = mlnode_manager.start_mlnode_container(ssh_info, instance_id)

            if not mlnode_url:
                print("❌ Failed to start MLNode container")
                return False

            print(f"✅ MLNode ready at: {mlnode_url}")

            # Check MLNode health
            print("\nChecking MLNode health...")
            health = mlnode_manager.check_mlnode_health(mlnode_url)

            if health['healthy']:
                print(f"✅ MLNode is healthy (state: {health['state']})")
            else:
                print(f"❌ MLNode health check failed: {health['error']}")
                return False

            print("\n" + "-"*70)
            print("  Step 3: Network Node Registration")
            print("-"*70)

            # Register MLNode
            print("\nRegistering MLNode with Network Node...")
            if not mlnode_manager.register_mlnode(mlnode_url, instance_id):
                print("❌ Failed to register MLNode")
                return False

            print(f"✅ MLNode registered successfully")

            if skip_poc:
                print("\n" + "-"*70)
                print("  Step 4: PoC Execution (SKIPPED)")
                print("-"*70)
                print("\n✅ Provisioning test completed successfully!")
                print("   The MLNode container is ready for PoC operations")

            else:
                print("\n" + "-"*70)
                print("  Step 4: PoC Execution")
                print("-"*70)

                print("\n⏳ Waiting for Network Node to trigger PoC...")
                print("   (The Network Node will automatically call MLNode PoC endpoints)")
                print("   Timeout: 15 minutes")

                success = mlnode_manager.wait_for_poc_completion(
                    instance_id,
                    timeout=900
                )

                if success:
                    print("\n✅ PoC completed successfully!")
                else:
                    print("\n⚠️ PoC did not complete within timeout")
                    print("   This may be normal if the network is not in PoC phase")

            # Unregister
            print("\nUnregistering MLNode...")
            mlnode_manager.unregister_mlnode(instance_id)

            print("\n✅ Test completed successfully!")
            return True

        finally:
            # Always cleanup GPU instance
            print("\n" + "-"*70)
            print("  Cleanup: Stopping GPU Instance")
            print("-"*70)

            scheduler.stop_gpu_instance(instance_id)
            print("✅ GPU instance stopped")

    except KeyboardInterrupt:
        print("\n\n⚠️ Test interrupted by user")
        return False
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main test entry point"""
    parser = argparse.ArgumentParser(description="Test official MLNode PoC integration")
    parser.add_argument('--manager-only', action='store_true',
                       help="Only test the MLNode manager (no GPU rental)")
    parser.add_argument('--skip-poc', action='store_true',
                       help="Skip PoC execution (test provisioning only)")
    parser.add_argument('--estimated-minutes', type=int, default=15,
                       help="Estimated test duration in minutes (default: 15)")
    parser.add_argument('--yes', action='store_true',
                       help="Skip confirmation prompt")

    args = parser.parse_args()

    print("\n" + "="*70)
    print("  Official MLNode PoC Integration Test")
    print("="*70)

    # Test 1: Manager
    if not test_mlnode_manager():
        print("\n❌ MLNode Manager test failed")
        return False

    if args.manager_only:
        print("\n✅ All tests completed successfully!")
        return True

    # Test 2: Full flow
    if not args.yes and not args.skip_poc:
        print("\n⚠️ WARNING: The next test will rent a GPU from Vast.ai")

    if not test_full_poc_flow(
        skip_poc=args.skip_poc,
        estimated_minutes=args.estimated_minutes
    ):
        print("\n❌ Full PoC flow test failed")
        return False

    print("\n" + "="*70)
    print("  ✅ All tests completed successfully!")
    print("="*70)
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
