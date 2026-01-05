#!/usr/bin/env python3
import sys
import os
import json
from datetime import datetime

# Add the scripts directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scripts'))

# Now import - note we import from the filename without .py
try:
    import importlib.util
    spec = importlib.util.spec_from_file_location("poc_monitor", "scripts/1_poc_monitor.py")
    poc_monitor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(poc_monitor)
    PoCMonitor = poc_monitor.PoCMonitor
except Exception as e:
    print(f"Error importing: {e}")
    print("\nPlease check that scripts/1_poc_monitor.py exists")
    sys.exit(1)

def test_connection():
    print("\n" + "="*60)
    print("  TEST: Blockchain Connectivity")
    print("="*60 + "\n")
    
    monitor = PoCMonitor()
    epoch_data = monitor.get_current_epoch()
    
    if epoch_data:
        print("✅ Successfully connected to Gonka node")
        print(f"\nEpoch Data:")
        print(json.dumps(epoch_data, indent=2))
        return True
    else:
        print("❌ Failed to connect to Gonka node")
        return False

if __name__ == "__main__":
    print("\n" + "="*60)
    print("  Gonka PoC Monitor - Quick Test")
    print("="*60)
    success = test_connection()
    sys.exit(0 if success else 1)
