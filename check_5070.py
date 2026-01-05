#!/usr/bin/env python3
import sys
import importlib.util
spec = importlib.util.spec_from_file_location("vastai_manager", "scripts/2_vastai_manager.py")
vastai = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vastai)

import os
os.environ['VASTAI_GPU_TYPE'] = 'RTX_5070_Ti'
os.environ['VASTAI_MAX_PRICE'] = '0.25'

manager = vastai.VastAIManager()
offers = manager.search_offers(limit=3)

if offers:
    print("\n✅ RTX 5070 Ti instances:\n")
    for offer in offers:
        print(f"Instance: {offer.id}")
        print(f"GPUs: {offer.num_gpus}x {offer.gpu_name}")
        print(f"VRAM per GPU: {offer.gpu_ram}GB")
        print(f"Total VRAM: {offer.gpu_ram * offer.num_gpus}GB")
        print(f"Price: ${offer.dph_total:.2f}/hr")
        print(f"10-min cost: ${(offer.dph_total/60)*10:.3f}")
        print(f"Monthly PoC: ${(offer.dph_total/60)*10*30:.2f}")
        print()
        
        if offer.gpu_ram * offer.num_gpus >= 40:
            print("✅ Meets 40GB VRAM minimum for PoC")
        else:
            print("⚠️  Below 40GB VRAM - may not work for PoC")
        print()
else:
    print("❌ No RTX 5070 Ti found either")
    print("\nLet's search for ANY available 2-GPU with 40GB+ total VRAM...")
    
    os.environ['VASTAI_GPU_TYPE'] = 'ANY'
    os.environ['VASTAI_MAX_PRICE'] = '0.50'
    os.environ['VASTAI_MIN_VRAM'] = '20'  # 20GB per GPU = 40GB total
    
    manager2 = vastai.VastAIManager()
    offers2 = manager2.search_offers(limit=5)
    
    if offers2:
        print("\n✅ Available options:\n")
        for offer in offers2:
            total_vram = offer.gpu_ram * offer.num_gpus
            if total_vram >= 40:
                print(f"✅ {offer.num_gpus}x {offer.gpu_name} - {total_vram}GB total")
                print(f"   ${offer.dph_total:.2f}/hr → ${(offer.dph_total/60)*10*30:.2f}/month")
                print()
