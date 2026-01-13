#!/usr/bin/env python3
"""
Live test: Rent GPU and deploy MLNode
This will cost money on Vast.ai and may take several minutes while the
container image downloads.
"""
import sys
import importlib.util
import argparse

# Load modules
spec = importlib.util.spec_from_file_location("poc_scheduler", "scripts/3_poc_scheduler.py")
scheduler_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scheduler_module)

parser = argparse.ArgumentParser(description="Run a live PoC test on Vast.ai.")
parser.add_argument(
    "--yes",
    action="store_true",
    help="Skip the confirmation prompt.",
)
args = parser.parse_args()

print("\n" + "="*60)
print("  LIVE POC TEST")
print("="*60)
print("\n⚠️  This will rent an actual GPU and may take several minutes")
print("⚠️  Large Docker images (13GB+) can take time to download")
print("Costs depend on your Vast.ai pricing limits")
if not args.yes:
    print("\nPress Enter to continue or Ctrl+C to cancel...")
    input()

scheduler = scheduler_module.PoCScheduler()

# Step 1: Find GPU
print("\nStep 1: Searching for GPU...")
offer_id = scheduler.select_best_gpu()
if not offer_id:
    print("❌ No GPU available")
    sys.exit(1)

# Step 2: Rent GPU
print("\nStep 2: Renting GPU...")
instance_id = scheduler.start_gpu_instance(offer_id)
if not instance_id:
    print("❌ Failed to rent GPU")
    sys.exit(1)

print(f"✅ GPU rented: Instance {instance_id}")

# Step 3: Deploy and test MLNode
print("\nStep 3: Deploying MLNode...")
try:
    success = scheduler.run_poc_sprint(instance_id)
    
    if success:
        print("\n✅ LIVE TEST PASSED!")
    else:
        print("\n⚠️  Test completed with warnings")
except Exception as e:
    print(f"\n❌ Test failed: {e}")
finally:
    # Step 4: Stop GPU
    print("\nStep 4: Stopping GPU...")
    scheduler.stop_gpu_instance(instance_id)
    print("✅ GPU stopped")

print("\n" + "="*60)
print("  Test Complete")
print("="*60)
