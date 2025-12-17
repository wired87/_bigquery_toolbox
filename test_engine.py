"""
Quick test to see if CoreEngine can initialize properly
"""
import sys
import traceback

try:
    print("Importing CoreEngine...")
    from engine import CoreEngine
    print("✅ Import successful")
    
    print("\nInitializing CoreEngine...")
    engine = CoreEngine()
    print("✅ Engine initialized successfully!")
    
except Exception as e:
    print(f"\n❌ Error: {e}")
    print("\nFull traceback:")
    traceback.print_exc()
    sys.exit(1)
