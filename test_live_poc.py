#!/usr/bin/env python3
"""
Live test: Rent GPU and deploy MLNode
This will cost money on Vast.ai and may take several minutes while the
container image downloads.
"""
import sys
import os
import time
import json
import logging
import importlib.util
import argparse

LOG_DIR = "logs"
INSTANCE_ID_PATH = os.path.join(LOG_DIR, "last_instance_id.txt")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "live_poc_test.log")),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("live_poc_test")

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency already in requirements.txt
    load_dotenv = None

if load_dotenv:
    load_dotenv("config/.env")
else:
    logger.warning("python-dotenv not installed; config/.env will not be loaded.")

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
parser.add_argument(
    "--max-cost",
    type=float,
    default=None,
    help="Abort if estimated cost exceeds this USD amount.",
)
parser.add_argument(
    "--estimated-minutes",
    type=int,
    default=int(os.getenv("POC_TEST_ESTIMATED_MINUTES", "30")),
    help="Estimated runtime in minutes for cost calculation (default: 30).",
)
parser.add_argument(
    "--keep-instance",
    action="store_true",
    help="Leave the instance running after the test (no auto stop).",
)
parser.add_argument(
    "--skip-poc",
    action="store_true",
    help="Skip the PoC sprint and only verify instance rental.",
)
args = parser.parse_args()

max_cost_env = os.getenv("MAX_TEST_COST_USD")
if args.max_cost is None and max_cost_env:
    try:
        args.max_cost = float(max_cost_env)
    except ValueError:
        logger.warning("Invalid MAX_TEST_COST_USD value; ignoring.")

print("\n" + "="*60)
print("  LIVE POC TEST")
print("="*60)
print("\n⚠️  This will rent an actual GPU and may take several minutes")
print("⚠️  Large Docker images (13GB+) can take time to download")
print("Costs depend on your Vast.ai pricing limits")
if args.max_cost is not None:
    print(f"Max estimated cost: ${args.max_cost:.2f}")
if not args.yes:
    print("\nPress Enter to continue or Ctrl+C to cancel...")
    input()

scheduler = scheduler_module.PoCScheduler()
start_time = time.time()

# Step 1: Find GPU
print("\nStep 1: Searching for GPU...")
offers = scheduler.vastai.search_offers(limit=5)
valid_offers = [o for o in offers if (o.gpu_ram * o.num_gpus) >= 40000]

if not valid_offers:
    print("❌ No GPU available")
    sys.exit(1)

valid_offers.sort(key=lambda offer: offer.dph_total)
print("\nTop offers:")
for idx, offer in enumerate(valid_offers[:3], start=1):
    est_cost = (offer.dph_total / 60) * args.estimated_minutes
    print(
        f"  {idx}. {offer.gpu_name} | VRAM: {offer.gpu_ram * offer.num_gpus / 1000:.1f}GB "
        f"| ${offer.dph_total:.3f}/hr | est ${est_cost:.3f}"
    )

best_offer = valid_offers[0]
estimated_cost = (best_offer.dph_total / 60) * args.estimated_minutes
logger.info(
    "Selected offer %s (%s) at $%.3f/hr, estimated $%.3f for %d minutes.",
    best_offer.id,
    best_offer.gpu_name,
    best_offer.dph_total,
    estimated_cost,
    args.estimated_minutes,
)

if args.max_cost is not None and estimated_cost > args.max_cost:
    print(
        f"❌ Estimated cost ${estimated_cost:.3f} exceeds max cost ${args.max_cost:.3f}. "
        "Aborting."
    )
    sys.exit(1)

# Step 2: Rent GPU
print("\nStep 2: Renting GPU...")
instance_id = scheduler.start_gpu_instance(best_offer.id)
if not instance_id:
    print("❌ Failed to rent GPU")
    sys.exit(1)

print(f"✅ GPU rented: Instance {instance_id}")
with open(INSTANCE_ID_PATH, "w", encoding="utf-8") as handle:
    handle.write(str(instance_id))
logger.info("Saved instance id %s to %s", instance_id, INSTANCE_ID_PATH)

# Step 3: Deploy and test MLNode
print("\nStep 3: Deploying MLNode...")
try:
    if args.skip_poc:
        print("\n⚠️  Skipping PoC sprint as requested.")
        success = True
    else:
        success = scheduler.run_poc_sprint(instance_id)

    if success:
        print("\n✅ LIVE TEST PASSED!")
    else:
        print("\n⚠️  Test completed with warnings")
except Exception as e:
    print(f"\n❌ Test failed: {e}")
finally:
    # Step 4: Stop GPU
    if args.keep_instance:
        print("\n⚠️  Leaving GPU running (keep-instance enabled).")
        print(f"Instance ID: {instance_id}")
    else:
        print("\nStep 4: Stopping GPU...")
        scheduler.stop_gpu_instance(instance_id)
        print("✅ GPU stopped")

elapsed = time.time() - start_time
print(f"\nElapsed time: {elapsed:.1f}s")
print("\n" + "="*60)
print("  Test Complete")
print("="*60)
