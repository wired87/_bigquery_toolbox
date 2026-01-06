import ray
import os
import logging
from typing import List

logger = logging.getLogger("bq_agent")

@ray.remote
class BQAgent:
    def __init__(self):
        self.urls = []
        # Pre-populate with default if available
        default_domain = os.getenv("DOMAIN", "localhost:8000")
        if default_domain:
            self.urls.append(self._format_url(default_domain))

    def _format_url(self, domain: str) -> str:
        if "localhost" in domain or "127.0.0.1" in domain:
            protocol = "ws"
        else:
            protocol = "wss"
        
        # Ensure we point to the chat endpoint
        base = f"{protocol}://{domain}"
        if not base.endswith("/"):
            base += "/"
        return f"{base}ws/chat/"

    def get_urls(self) -> List[str]:
        return self.urls

    def register_url(self, url: str):
        if url not in self.urls:
            self.urls.append(url)
            
    def unregister_url(self, url: str):
        if url in self.urls:
            self.urls.remove(url)

