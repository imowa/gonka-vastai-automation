#!/usr/bin/env python3
import sys
import importlib.util
spec = importlib.util.spec_from_file_location("vastai_manager", "scripts/2_vastai_manager.py")
vastai = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vastai)

import os
os.environ['VASTAI_GPU_TYPE'] = 'RTX_3090'
os.environ['VASTAI_MAX_PRICE'] = '0.30'

manager = vastai.VastAIManager()
offers = manager.search_offers(limit=3)

if offers:
    print("\n✅ RTX 3090 instances available:\n")
    for offer in offers:
        print(f"Instance: {offer.id}")
        print(f"GPUs: {offer.num_gpus}x {offer.gpu_name}")
        print(f"VRAM per GPU: {offer.gpu_ram}GB")
        print(f"Total VRAM: {offer.gpu_ram * offer.num_gpus}GB")
        print(f"Price: ${offer.dph_total:.2f}/hr")
        print(f"Network: ↑{offer.inet_up:.0f} Mbps ↓{offer.inet_down:.0f} Mbps")
        print()
else:
    print("❌ No RTX 3090 instances found")
