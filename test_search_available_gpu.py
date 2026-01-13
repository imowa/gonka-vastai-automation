#!/usr/bin/env python3
"""
Simple helper to test Vast.ai GPU availability.
"""
import argparse
import importlib.util
import os
import time

spec = importlib.util.spec_from_file_location("vastai_manager", "scripts/2_vastai_manager.py")
manager_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manager_module)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Search for available Vast.ai GPU offers.")
    parser.add_argument("--gpu-type", default=os.getenv("VASTAI_GPU_TYPE", "ANY"))
    parser.add_argument("--num-gpus", type=int, default=int(os.getenv("VASTAI_NUM_GPUS", "1")))
    parser.add_argument("--min-vram", type=int, default=int(os.getenv("VASTAI_MIN_VRAM", "24")))
    parser.add_argument("--max-price", type=float, default=float(os.getenv("VASTAI_MAX_PRICE", "0.50")))
    parser.add_argument("--disk-size", type=int, default=int(os.getenv("VASTAI_DISK_SIZE", "50")))
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--retries", type=int, default=99)
    parser.add_argument("--interval", type=int, default=15, help="Seconds between retries.")
    return parser


def main() -> int:
    args = build_parser().parse_args()

    os.environ["VASTAI_GPU_TYPE"] = args.gpu_type
    os.environ["VASTAI_NUM_GPUS"] = str(args.num_gpus)
    os.environ["VASTAI_MIN_VRAM"] = str(args.min_vram)
    os.environ["VASTAI_MAX_PRICE"] = str(args.max_price)
    os.environ["VASTAI_DISK_SIZE"] = str(args.disk_size)

    print("\n" + "=" * 60)
    print("  TEST: SEARCH AVAILABLE GPUS")
    print("=" * 60)
    print("\nConfiguration:")
    print(f"  GPU Type: {args.gpu_type}")
    print(f"  GPU Count: {args.num_gpus}")
    print(f"  Min VRAM: {args.min_vram} GB")
    print(f"  Max Price: ${args.max_price}/hr")
    print(f"  Disk Size: {args.disk_size} GB")
    print(f"  Retries: {args.retries} (interval {args.interval}s)")

    manager = manager_module.VastAIManager()

    for attempt in range(1, max(1, args.retries) + 1):
        offers = manager.search_offers(limit=args.limit)
        if offers:
            print(f"\n✅ Found {len(offers)} offer(s):\n")
            for idx, offer in enumerate(offers, start=1):
                print(
                    f"{idx}. {offer.gpu_name} | {offer.num_gpus}x | "
                    f"VRAM: {offer.gpu_ram * offer.num_gpus / 1000:.1f}GB | "
                    f"${offer.dph_total:.3f}/hr | Host {offer.host_id}"
                )
                print(f"   Upload: {offer.inet_up:.0f} Mbps, Download: {offer.inet_down:.0f} Mbps")
            return 0

        if attempt < args.retries:
            print(f"⚠️  No offers found (attempt {attempt}/{args.retries}). Retrying in {args.interval}s...")
            time.sleep(args.interval)

    print("\n❌ No offers found after retries.")
    print("Try adjusting:")
    print("  - --max-price (increase if needed)")
    print("  - --gpu-type ANY (broaden match)")
    print("  - --min-vram (lower the requirement)")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
