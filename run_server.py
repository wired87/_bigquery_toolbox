import os
import sys
import subprocess
import time
import socket

# Import global server configuration
from server_config import GlobalServerConfig

# Deferred imports for Ray inside main()

def is_port_available(port, host='127.0.0.1'):
    """Check if a port is available for binding."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((host, port))
            return True
    except OSError:
        return False

def find_available_port(start_port=8000, max_attempts=10, host='127.0.0.1'):
    """Find an available port starting from start_port."""
    for port in range(start_port, start_port + max_attempts):
        if is_port_available(port, host):
            return port
    raise RuntimeError(f"Could not find available port in range {start_port}-{start_port + max_attempts - 1}")

def main():
    print("🚀 Starting BigQuery AIToolbox Engine...")
    
    # 1. Initialize Ray
    ray_available = False
    try:
        import ray
        from agent import BQAgent
        ray_available = True
    except ImportError:
        print("⚠️  Ray not installed (likely Python version mismatch). Skipping Ray service discovery.")
        # Proceed without Ray

    if ray_available:
        try:
            # Check if Ray is already running (e.g. via 'ray start')
            # If not, init locally
            ray.init(address="auto", ignore_reinit_error=True)
            print("✅ Connected to existing Ray cluster.")
        except:
            print("⚠️  No Ray cluster found. Starting local Ray instance...")
            try:
                ray.init(ignore_reinit_error=True)
                print("✅ Ray initialized locally.")
            except Exception as e:
                print(f"❌ Failed to init Ray locally: {e}")
                ray_available = False

    # 2. Start BQAgent Actor
    if ray_available:
        try:
            # Check if actor exists
            try:
                ray.get_actor("bq_agent")
                print("✅ BQAgent actor already running.")
            except ValueError:
                # Create actor
                agent = BQAgent.options(name="bq_agent", lifetime="detached").remote()
                print("✅ BQAgent actor started (detached).")
                
                # Register default URL
                domain = os.getenv("DOMAIN", "localhost:8000")
                # We can't await in sync main, but the actor init handles env var default
        except Exception as e:
            print(f"❌ Failed to start Ray actor: {e}")
            # Don't exit, just continue to Daphne


    # 3. Start Daphne Server
    print("🚀 Starting Daphne ASGI Server...")
    
    # Find available port
    default_port = 8000
    try:
        port = find_available_port(start_port=default_port, max_attempts=10)
        if port != default_port:
            print(f"⚠️  Port {default_port} is already in use. Jumping to port {port}...")
        else:
            print(f"✅ Using port {port}")
    except RuntimeError as e:
        print(f"❌ {e}")
        sys.exit(1)
    
    # Initialize global server configuration
    try:
        GlobalServerConfig.initialize(port=port, host="127.0.0.1", protocol="ws")
        print(f"🌍 Server info available globally:")
        print(f"   - HTTP: {GlobalServerConfig.get_http_url()}")
        print(f"   - WebSocket: {GlobalServerConfig.get_ws_url()}")
    except Exception as config_error:
        print(f"⚠️  Could not initialize global config: {config_error}")
    
    # Locate daphne executable relative to python interpreter
    daphne_cmd = "daphne"
    scripts_dir = os.path.dirname(sys.executable)
    possible_daphne = os.path.join(scripts_dir, "daphne.exe" if os.name == 'nt' else "daphne")
    
    if os.path.exists(possible_daphne):
        daphne_cmd = possible_daphne
    else:
        # Fallback to module execution if executable not found
        daphne_cmd = [sys.executable, "-m", "daphne"]
        
    if isinstance(daphne_cmd, str):
        cmd = [
            daphne_cmd, 
            "-b", "127.0.0.1", 
            "-p", str(port), 
            "--application-close-timeout", "120",
            "--websocket_timeout", "180",  # Extended for long AI operations
            "config.asgi:application"
        ]
    else:
        cmd = daphne_cmd + [
            "-b", "127.0.0.1", 
            "-p", str(port), 
            "--application-close-timeout", "120",
            "--websocket_timeout", "180",  # Extended for long AI operations
            "config.asgi:application"
        ]

    
    # Add project root to PYTHONPATH
    env = os.environ.copy()
    env["PYTHONPATH"] = os.getcwd()
    
    try:
        # Run daphne as a subprocess
        process = subprocess.Popen(cmd, env=env)
        process.wait()
    except KeyboardInterrupt:
        print("\nStopping server...")
        process.terminate()
        if 'ray' in locals() and ray_available:
             try:
                ray.shutdown()
             except:
                pass
        print("Bye!")

if __name__ == "__main__":
    main()
