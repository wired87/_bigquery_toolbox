import os
import json
from typing import Set
import logging

# Configure Logging
logger = logging.getLogger(__name__)

BLOCKED_IPS_FILE = "blocked_ips.json"
ACCESS_LOG_FILE = "access_log.txt"

class IpManager:
    def __init__(self):
        self.blocked_ips: Set[str] = set()
        self.load_blocked_ips()

    def load_blocked_ips(self):
        """Loads blocked IPs from a JSON file."""
        if os.path.exists(BLOCKED_IPS_FILE):
            try:
                with open(BLOCKED_IPS_FILE, 'r') as f:
                    data = json.load(f)
                    self.blocked_ips = set(data.get("blocked_ips", []))
                print(f"Loaded {len(self.blocked_ips)} blocked IPs.")
            except Exception as e:
                print(f"Error loading blocked IPs: {e}")
        else:
             # Create empty file if not exists
             self.save_blocked_ips()

    def block_ip(self, ip: str):
        """Blocks an IP address."""
        self.blocked_ips.add(ip)
        self.save_blocked_ips()
        print(f"Blocked IP: {ip}")
        
    def unblock_ip(self, ip: str):
        """Unblocks an IP address."""
        if ip in self.blocked_ips:
            self.blocked_ips.remove(ip)
            self.save_blocked_ips()
            print(f"Unblocked IP: {ip}")

    def save_blocked_ips(self):
        """Saves current blocked IPs to the JSON file."""
        try:
            with open(BLOCKED_IPS_FILE, 'w') as f:
                json.dump({"blocked_ips": list(self.blocked_ips)}, f, indent=4)
        except Exception as e:
             print(f"Error saving blocked IPs: {e}")

    def is_blocked(self, ip: str) -> bool:
        """Checks if an IP is blocked."""
        # Reloading to ensure external updates are caught? 
        # For high perf, maybe just reload periodically, but for now this is fine or rely on init.
        # Let's rely on in-memory for speed, keeping it simple.
        # If we want dynamic updates from file edits, we'd need to check file mtime.
        return ip in self.blocked_ips

    def log_access(self, ip: str, endpoint: str, blocked: bool = False):
        """Logs an access attempt."""
        try:
            with open(ACCESS_LOG_FILE, 'a') as f:
                import datetime
                timestamp = datetime.datetime.now().isoformat()
                status = "BLOCKED" if blocked else "ALLOWED"
                f.write(f"{timestamp} | {ip} | {status} | {endpoint}\n")
        except Exception as e:
            print(f"Error writing to access log: {e}")

# Global instance
ip_manager = IpManager()
