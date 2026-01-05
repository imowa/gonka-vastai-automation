#!/usr/bin/env python3
import sys
import os
import importlib.util

# Load the manager
spec = importlib.util.spec_from_file_location("vastai_manager", "scripts/2_vastai_manager.py")
vastai = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vastai)

# Override settings
os.environ['VASTAI_MAX_PRICE'] = '2.00'
os.environ['VASTAI_GPU_TYPE'] = 'ANY'

# Search
manager = vastai.VastAIManager()
offers = manager.search_offers(limit=10)

print("\n🔍 Available 2-GPU instances:\n")
if offers:
    for i, offer in enumerate(offers, 1):
        print(f"{i}. {offer}")
        cost_per_10min = (offer.dph_total / 60) * 10
        print(f"   💰 Cost for 10-min PoC: ${cost_per_10min:.3f}")
        print(f"   📊 Monthly (daily PoC): ${cost_per_10min * 30:.2f}")
        print()
else:
    print("No 2-GPU instances found. This is unusual.")
    print("\nTrying single GPU with 40GB+ VRAM instead...")
    os.environ['VASTAI_MIN_VRAM'] = '40'
    manager2 = vastai.VastAIManager()
    manager2.num_gpus = 1
    offers2 = manager2.search_offers(limit=5)
    
    if offers2:
        print("\n✅ Single GPU alternatives (40GB+ VRAM):\n")
        for i, offer in enumerate(offers2, 1):
            print(f"{i}. {offer}")
            cost_per_10min = (offer.dph_total / 60) * 10
            print(f"   💰 Cost for 10-min PoC: ${cost_per_10min:.3f}")
            print()
