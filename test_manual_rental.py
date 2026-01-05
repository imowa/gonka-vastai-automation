#!/usr/bin/env python3
import sys
import importlib.util

spec = importlib.util.spec_from_file_location("vastai", "scripts/2_vastai_manager.py")
vastai = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vastai)

print("\n⚠️  MANUAL GPU RENTAL TEST")
print("This will actually rent a GPU for ~1 minute")
print("Estimated cost: $0.005 (half a cent)")
print("\nPress Enter to continue or Ctrl+C to cancel...")
input()

manager = vastai.VastAIManager()

# Find cheapest GPU
offers = manager.search_offers(limit=1)
if not offers:
    print("❌ No GPU available")
    sys.exit(1)

offer = offers[0]
print(f"\n✅ Found: {offer}")

# Rent it
instance_id = manager.create_instance(offer.id)
if not instance_id:
    print("❌ Failed to create instance")
    sys.exit(1)

print(f"✅ Instance created: {instance_id}")
print("Waiting 60 seconds...")

import time
time.sleep(60)

# Stop it
print("\nStopping instance...")
manager.destroy_instance(instance_id)

cost = manager.get_instance_cost(instance_id)
print(f"\n✅ Test complete!")
print(f"Total cost: ${cost:.4f}" if cost else "Cost unavailable")
