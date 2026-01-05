#!/usr/bin/env python3
"""
Test PoC Scheduler
Dry-run test without actually renting GPU
"""

import sys
import os
import importlib.util

# Load scheduler
spec = importlib.util.spec_from_file_location("poc_scheduler", "scripts/3_poc_scheduler.py")
scheduler_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scheduler_module)

PoCScheduler = scheduler_module.PoCScheduler


def test_initialization():
    """Test 1: Can we initialize the scheduler?"""
    print("\n" + "="*60)
    print("  TEST 1: Scheduler Initialization")
    print("="*60 + "\n")
    
    try:
        scheduler = PoCScheduler()
        print("✅ Scheduler initialized successfully")
        print(f"\nConfiguration:")
        print(f"  Prep time: {scheduler.prep_time}s ({scheduler.prep_time//60} min)")
        print(f"  Check interval: {scheduler.check_interval}s")
        print(f"  Max daily spend: ${scheduler.max_daily_spend}")
        print(f"  Max duration: {scheduler.max_duration}s ({scheduler.max_duration//3600}h)")
        return True
    except Exception as e:
        print(f"❌ Initialization failed: {e}")
        return False


def test_blockchain_monitoring():
    """Test 2: Can we monitor the blockchain?"""
    print("\n" + "="*60)
    print("  TEST 2: Blockchain Monitoring")
    print("="*60 + "\n")
    
    try:
        scheduler = PoCScheduler()
        status = scheduler.monitor.get_status()
        
        if status['status'] == 'active':
            print("✅ Blockchain monitoring working")
            print(f"\nCurrent status:")
            print(f"  Epoch: {status['current_epoch']}")
            print(f"  Phase: {status['current_phase']}")
            print(f"  Next PoC: {status['seconds_to_poc']}s")
            
            hours = status['seconds_to_poc'] // 3600
            minutes = (status['seconds_to_poc'] % 3600) // 60
            print(f"  Time to PoC: {hours}h {minutes}m")
            
            if status['should_start_gpu']:
                print("\n🚨 GPU should START NOW!")
            else:
                print("\n💤 No action needed yet")
            
            return True
        else:
            print("❌ Cannot fetch blockchain data")
            return False
    
    except Exception as e:
        print(f"❌ Monitoring failed: {e}")
        return False


def test_gpu_search():
    """Test 3: Can we find available GPUs?"""
    print("\n" + "="*60)
    print("  TEST 3: GPU Search")
    print("="*60 + "\n")
    
    try:
        scheduler = PoCScheduler()
        offer_id = scheduler.select_best_gpu()
        
        if offer_id:
            print(f"✅ Found GPU offer: {offer_id}")
            
            # Get offer details
            offers = scheduler.vastai.search_offers(limit=1)
            if offers:
                offer = offers[0]
                print(f"\nSelected GPU:")
                print(f"  Type: {offer.num_gpus}x {offer.gpu_name}")
                print(f"  VRAM: {offer.gpu_ram * offer.num_gpus // 1024}GB total")
                print(f"  Price: ${offer.dph_total:.2f}/hr")
                
                cost_10min = (offer.dph_total / 60) * 10
                cost_monthly = cost_10min * 30
                print(f"\nCost estimates:")
                print(f"  10-min PoC: ${cost_10min:.3f}")
                print(f"  Monthly (30 days): ${cost_monthly:.2f}")
            
            return True
        else:
            print("❌ No suitable GPU found")
            print("\nTry adjusting config/.env:")
            print("  - Increase VASTAI_MAX_PRICE")
            print("  - Change VASTAI_GPU_TYPE to 'ANY'")
            return False
    
    except Exception as e:
        print(f"❌ GPU search failed: {e}")
        return False


def test_spending_limits():
    """Test 4: Spending limit checks"""
    print("\n" + "="*60)
    print("  TEST 4: Spending Limits")
    print("="*60 + "\n")
    
    try:
        scheduler = PoCScheduler()
        
        print(f"Daily spend limit: ${scheduler.max_daily_spend}")
        print(f"Current spend: ${scheduler.daily_spend}")
        
        if scheduler.check_spending_limit():
            print("✅ Within spending limits")
            remaining = scheduler.max_daily_spend - scheduler.daily_spend
            print(f"Remaining budget: ${remaining:.2f}")
            return True
        else:
            print("⚠️  Spending limit reached")
            return False
    
    except Exception as e:
        print(f"❌ Spending check failed: {e}")
        return False


def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("  PoC Scheduler - Test Suite")
    print("="*60)
    
    tests = [
        ("Initialization", test_initialization),
        ("Blockchain Monitoring", test_blockchain_monitoring),
        ("GPU Search", test_gpu_search),
        ("Spending Limits", test_spending_limits),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"\n❌ Test crashed: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "="*60)
    print("  TEST SUMMARY")
    print("="*60 + "\n")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test_name}")
    
    print(f"\n{passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed!")
        print("\n" + "="*60)
        print("  Ready for Production!")
        print("="*60)
        print("\nTo run the scheduler:")
        print("  python scripts/3_poc_scheduler.py")
        print("\nThis will:")
        print("  1. Monitor blockchain every 5 minutes")
        print("  2. Start GPU 30 min before PoC")
        print("  3. Run PoC Sprint automatically")
        print("  4. Stop GPU after completion")
        print("  5. Cost: ~$1-2/month for PoC")
    else:
        print("\n⚠️  Some tests failed")
        print("Fix the issues above before running in production")
    
    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
