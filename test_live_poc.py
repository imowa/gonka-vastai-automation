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
    "--estimated-minutes",
    type=int,
    default=15,
    help="Estimated runtime for cost calculation (minutes).",
)
parser.add_argument(
    "--max-cost",
    type=float,
    default=None,
    help="Abort if estimated cost exceeds this amount.",
)
parser.add_argument(
    "--skip-poc",
    action="store_true",
    help="Skip the PoC sprint execution after renting the GPU.",
)
parser.add_argument(
    "--docker-image",
    default=os.getenv("DOCKER_IMAGE", os.getenv("VASTAI_DOCKER_IMAGE", "vllm/vllm-openai:latest")),
    help="Docker image to use (default: official MLNode image or vllm/vllm-openai:latest).",
)
parser.add_argument(
    "--wait-timeout",
    type=int,
    default=int(os.getenv("VLLM_STARTUP_TIMEOUT", "1800")),
    help="Maximum time to wait for vLLM to be ready (seconds).",
)
parser.add_argument(
    "--search-retries",
    type=int,
    default=int(os.getenv("VASTAI_SEARCH_RETRIES", "99")),
    help="Number of times to retry the GPU search before failing.",
)
parser.add_argument(
    "--search-interval",
    type=int,
    default=int(os.getenv("VASTAI_SEARCH_INTERVAL", "15")),
    help="Seconds to wait between GPU search attempts.",
)
parser.add_argument(
    "--keep-instance",
    action="store_true",
    help="Leave the GPU instance running instead of stopping it.",
)
args = parser.parse_args()

if args.wait_timeout:
    os.environ["VLLM_STARTUP_TIMEOUT"] = str(args.wait_timeout)
if args.docker_image:
    os.environ["DOCKER_IMAGE"] = args.docker_image
    os.environ["VASTAI_DOCKER_IMAGE"] = args.docker_image

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("test_live_poc")

os.makedirs("logs", exist_ok=True)
INSTANCE_ID_PATH = os.path.join("logs", "last_instance_id.txt")

print("\n" + "="*60)
print("  LIVE POC TEST - DUAL MODEL STRATEGY")
print("="*60)
print("\n📊 Configuration:")
print(f"  PoC Model (GPU): {os.getenv('MLNODE_POC_MODEL', 'Qwen/Qwen2.5-7B-Instruct')}")
print(f"  Inference Model (API): {os.getenv('MLNODE_INFERENCE_MODEL', 'Qwen/QwQ-32B')}")
print(f"  GPU Count: {os.getenv('VASTAI_NUM_GPUS', '1')}")
print(f"  Max GPU Price: ${os.getenv('VASTAI_MAX_PRICE', '0.30')}/hr")
print(f"  Min Total VRAM: {os.getenv('VASTAI_MIN_TOTAL_VRAM', '40')}GB")
print("\n⚠️  This will rent an actual GPU and may take several minutes")
print("⚠️  Large Docker images (13GB+) can take time to download")
print("Costs depend on your Vast.ai pricing limits")
if not args.yes:
    print("\nPress Enter to continue or Ctrl+C to cancel...")
    input()

scheduler = scheduler_module.PoCScheduler()
start_time = time.time()
min_total_vram_gb = int(os.getenv("VASTAI_MIN_TOTAL_VRAM", "40"))

# Step 1: Find GPU
print("\nStep 1: Searching for GPU...")
valid_offers = []
search_attempt = 0

while search_attempt < max(1, args.search_retries):
    search_attempt += 1
    blocked_offer_ids = scheduler.vastai.get_blocked_offer_ids()
    blocked_host_ids = scheduler.vastai.get_blocked_host_ids()
    offers = scheduler.vastai.search_offers(
        limit=5,
        exclude_offer_ids=blocked_offer_ids,
        exclude_host_ids=blocked_host_ids,
    )
    valid_offers = [
        o
        for o in offers
        if (o.gpu_ram * o.num_gpus) >= (min_total_vram_gb * 1000)
    ]
    if valid_offers:
        break

    if search_attempt < args.search_retries:
        if offers:
            print(
                f"ℹ️  Found {len(offers)} offer(s), but none meet "
                f"the {min_total_vram_gb}GB total VRAM requirement."
            )
            for offer in offers:
                total_vram = offer.gpu_ram * offer.num_gpus / 1000
                print(
                    f"   - {offer.gpu_name} | {offer.num_gpus}x | "
                    f"VRAM: {total_vram:.1f}GB | ${offer.dph_total:.3f}/hr"
                )
        print(
            f"⚠️  No GPU available (attempt {search_attempt}/{args.search_retries}). "
            f"Retrying in {args.search_interval}s..."
        )
        time.sleep(args.search_interval)

if not valid_offers:
    print("❌ No GPU available after retries")
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
instance_id = scheduler.start_gpu_instance_with_retries(
    preferred_offer_id=best_offer.id,
    docker_image=args.docker_image,
)
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
