import importlib.util

spec = importlib.util.spec_from_file_location("vastai", "scripts/2_vastai_manager.py")
vastai = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vastai)

# Test what status field Vast.ai actually returns
manager = vastai.VastAIManager()
instances = manager.list_my_instances()

if instances:
    print("Current instances and their status fields:")
    for inst in instances:
        print(f"\nInstance {inst['id']}:")
        print(f"  Status fields available: {[k for k in inst.keys() if 'stat' in k.lower()]}")
        for key in inst.keys():
            if 'stat' in key.lower() or 'state' in key.lower():
                print(f"    {key}: {inst[key]}")
else:
    print("No instances to check")
