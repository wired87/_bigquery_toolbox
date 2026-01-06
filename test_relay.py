"""
Test script to demonstrate RELAY package discovery
Sets environment variables and monitors discovery
"""

import os
import sys
import time
import json

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def set_relay_modules():
    """Set example RELAY environment variables"""
    
    examples = {
        "RELAY_EXPORT_CSV": {
            "key": "export_to_csv",
            "description": "Export query results to CSV file",
            "pattern": r"export|download|save\s+(to\s+)?csv",
            "priority": 85,
            "action": "export_csv"
        },
        "RELAY_SUMMARIZE": {
            "key": "summarize_content",
            "description": "Summarize document content",
            "pattern": r"summarize|summary|tldr",
            "priority": 80,
            "action": "generate_summary"
        },
        "RELAY_TRANSLATE": {
            "key": "translate_text",
            "description": "Translate content to another language",
            "pattern": r"translate|translation",
            "priority": 75,
            "action": "perform_translation"
        }
    }
    
    print("=" * 60)
    print("Setting RELAY Environment Variables")
    print("=" * 60)
    
    for key, config in examples.items():
        json_value = json.dumps(config)
        os.environ[key] = json_value
        print(f"\n✅ Set {key}")
        print(f"   Key: {config['key']}")
        print(f"   Description: {config['description']}")
        print(f"   Pattern: {config['pattern']}")
        print(f"   Priority: {config['priority']}")
    
    print("\n" + "=" * 60)
    print("RELAY modules have been set!")
    print("=" * 60)
    print("\n🔍 The validator scanner will discover these in ~5 seconds")
    print("📡 Frontend clients will be notified in real-time\n")

def demonstrate_rag_access():
    """Demonstrate RAG package usage"""
    
    print("\n" + "=" * 60)
    print("RAG Package Demonstration")
    print("=" * 60)
    
    try:
        from rag import get_rag_instance
        from rag.global_registry import GlobalRAGRegistry
        
        print("\n✅ RAG package imported successfully")
        
        # Check if initialized
        if GlobalRAGRegistry.is_initialized():
            print("✅ Global RAG Registry is initialized")
            
            rag = get_rag_instance()
            print("✅ Retrieved RAG instance")
            
            # Get stats
            stats = rag.get_stats()
            print(f"\n📊 RAG Statistics:")
            print(f"   - Active Requests: {stats.get('active_requests', 0)}")
            print(f"   - Total Processed: {stats.get('total_processed', 0)}")
            print(f"   - Engine Authenticated: {stats.get('engine_authenticated', False)}")
            print(f"   - Current User: {stats.get('current_user', 'None')}")
            
            # Get discovered RELAY modules
            discovered = GlobalRAGRegistry.get_discovered_relays()
            print(f"\n🔌 Discovered RELAY Modules: {len(discovered)}")
            for module in discovered:
                print(f"   - {module['key']}: {module['description']}")
        else:
            print("⚠️  Global RAG Registry not initialized")
            print("   This is normal if the server hasn't started yet")
            
    except ImportError as e:
        print(f"⚠️  RAG package not available: {e}")
        print("   This is expected if running outside the server context")
    
    print("\n" + "=" * 60)

def monitor_environment():
    """Monitor RELAY environment variables"""
    
    print("\n" + "=" * 60)
    print("Current RELAY Environment Variables")
    print("=" * 60)
    
    relay_vars = {k: v for k, v in os.environ.items() if k.startswith("RELAY_")}
    
    if relay_vars:
        print(f"\n✅ Found {len(relay_vars)} RELAY variables:\n")
        for key, value in relay_vars.items():
            try:
                config = json.loads(value)
                print(f"📦 {key}")
                print(f"   Key: {config.get('key', 'N/A')}")
                print(f"   Description: {config.get('description', 'N/A')}")
                print(f"   Priority: {config.get('priority', 'N/A')}")
                print()
            except json.JSONDecodeError:
                print(f"⚠️  {key}: Invalid JSON")
                print()
    else:
        print("\n⚠️  No RELAY variables found")
        print("   Run set_relay_modules() first")
    
    print("=" * 60)

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="RELAY Module Test Utility")
    parser.add_argument('--set', action='store_true', help='Set example RELAY modules')
    parser.add_argument('--monitor', action='store_true', help='Monitor current RELAY variables')
    parser.add_argument('--demo', action='store_true', help='Demonstrate RAG package access')
    parser.add_argument('--all', action='store_true', help='Run all tests')
    
    args = parser.parse_args()
    
    if args.all or not any([args.set, args.monitor, args.demo]):
        # Run everything
        set_relay_modules()
        time.sleep(1)
        monitor_environment()
        demonstrate_rag_access()
    else:
        if args.set:
            set_relay_modules()
        if args.monitor:
            monitor_environment()
        if args.demo:
            demonstrate_rag_access()
    
    print("\n✅ Test completed!\n")
