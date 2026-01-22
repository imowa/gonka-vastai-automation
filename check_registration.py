#!/usr/bin/env python3
"""
Check and manage MLNode registrations in Admin API

Usage:
    python3 check_registration.py              # List all registered nodes
    python3 check_registration.py --clean      # Remove stale nodes
    python3 check_registration.py --node-only  # Only show MLNode entries
"""

import sys
import os
import json
import requests
import argparse
from dotenv import load_dotenv

load_dotenv('config/.env')

ADMIN_API = os.getenv('GONKA_ADMIN_API_URL', 'http://localhost:9200')

def get_nodes():
    """Fetch all registered nodes"""
    try:
        response = requests.get(f"{ADMIN_API}/admin/v1/nodes", timeout=10)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"❌ Failed to fetch nodes: HTTP {response.status_code}")
            return None
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

def list_nodes(nodes, mlnode_only=False):
    """Display registered nodes"""
    if not nodes:
        print("No nodes found")
        return

    print("\n" + "="*80)
    print("Registered Nodes in Admin API")
    print("="*80)

    for node in nodes:
        node_info = node.get('node', {})
        node_id = node_info.get('id', 'UNKNOWN')
        state = node.get('state', {})
        admin_state = state.get('admin_state', {})

        # Filter for MLNode only if requested
        if mlnode_only and not node_id.startswith('vastai-mlnode'):
            continue

        print(f"\nNode ID: {node_id}")
        print(f"  Host: {node_info.get('host', 'N/A')}")
        print(f"  Ports: inference={node_info.get('inference_port')}, poc={node_info.get('poc_port')}")
        print(f"  Models: {', '.join(node_info.get('models', {}).keys())}")
        print(f"  Status: {state.get('current_status', 'UNKNOWN')}")
        print(f"  Epoch: {admin_state.get('epoch', 'UNKNOWN')}")
        print(f"  Enabled: {admin_state.get('enabled', 'N/A')}")

def delete_node(node_id):
    """Delete a node from Admin API"""
    try:
        response = requests.delete(f"{ADMIN_API}/admin/v1/nodes/{node_id}", timeout=10)

        if response.status_code == 200:
            print(f"✅ Deleted: {node_id}")
            return True
        elif response.status_code == 404:
            print(f"⚠️  Not found: {node_id} (already deleted?)")
            return True
        else:
            print(f"❌ Failed to delete {node_id}: HTTP {response.status_code}")
            return False

    except Exception as e:
        print(f"❌ Error deleting {node_id}: {e}")
        return False

def clean_registrations(nodes):
    """Remove stale/test nodes"""
    if not nodes:
        print("No nodes to clean")
        return

    to_delete = []

    for node in nodes:
        node_info = node.get('node', {})
        node_id = node_info.get('id', '')

        # Remove Vast.ai ephemeral MLNodes (they should be cleaned up automatically)
        if node_id.startswith('vastai-mlnode'):
            to_delete.append((node_id, "Ephemeral Vast.ai MLNode (should cleanup automatically)"))

        # Remove proxy if it has poc_port (shouldn't have it)
        if node_id == 'hyperbolic-proxy-1':
            poc_port = node_info.get('poc_port')
            if poc_port and poc_port > 0:
                to_delete.append((node_id, f"Proxy has poc_port={poc_port} (inference-only, remove poc)"))

    if not to_delete:
        print("✅ No stale registrations found")
        return

    print("\n" + "="*80)
    print(f"Found {len(to_delete)} stale registration(s) to remove:")
    print("="*80)

    for node_id, reason in to_delete:
        print(f"\n{node_id}")
        print(f"  Reason: {reason}")

    response = input("\nDelete these registrations? (yes/no): ").lower()
    if response in ['yes', 'y']:
        for node_id, _ in to_delete:
            delete_node(node_id)
        print("\n✅ Cleanup complete")
    else:
        print("Cancelled")

def main():
    parser = argparse.ArgumentParser(description='Check MLNode registrations in Admin API')
    parser.add_argument('--clean', action='store_true', help='Remove stale nodes')
    parser.add_argument('--node-only', action='store_true', help='Only show MLNode entries')
    parser.add_argument('--delete', type=str, help='Delete specific node ID')
    args = parser.parse_args()

    print(f"Admin API: {ADMIN_API}")

    nodes = get_nodes()
    if nodes is None:
        sys.exit(1)

    if args.delete:
        delete_node(args.delete)
    elif args.clean:
        clean_registrations(nodes)
    else:
        list_nodes(nodes, mlnode_only=args.node_only)

    print()

if __name__ == "__main__":
    main()
