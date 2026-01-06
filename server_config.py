"""
Global Server Configuration
Exposes server runtime information globally for all components
"""

from dataclasses import dataclass, field
from typing import Optional
import threading
from datetime import datetime


@dataclass
class ServerConfig:
    """
    Global server configuration dataclass
    Thread-safe singleton for runtime server information
    """
    port: Optional[int] = None
    host: str = "127.0.0.1"
    started_at: Optional[datetime] = None
    protocol: str = "ws"
    is_running: bool = False
    
    @property
    def ws_url(self) -> str:
        """Get the WebSocket URL"""
        if self.port:
            return f"{self.protocol}://{self.host}:{self.port}/ws/chat/"
        return f"{self.protocol}://{self.host}:8000/ws/chat/"
    
    @property
    def http_url(self) -> str:
        """Get the HTTP URL"""
        if self.port:
            return f"http://{self.host}:{self.port}"
        return f"http://{self.host}:8000"
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization"""
        return {
            'port': self.port,
            'host': self.host,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'protocol': self.protocol,
            'is_running': self.is_running,
            'ws_url': self.ws_url,
            'http_url': self.http_url
        }


class GlobalServerConfig:
    """
    Global singleton for server configuration
    Provides thread-safe access to server runtime information
    """
    
    _instance: Optional[ServerConfig] = None
    _lock = threading.Lock()
    
    @classmethod
    def initialize(cls, port: int, host: str = "127.0.0.1", protocol: str = "ws"):
        """
        Initialize the global server configuration
        
        Args:
            port: Server port number
            host: Server host address
            protocol: WebSocket protocol (ws or wss)
        """
        with cls._lock:
            cls._instance = ServerConfig(
                port=port,
                host=host,
                started_at=datetime.now(),
                protocol=protocol,
                is_running=True
            )
            print(f"✅ Global Server Config initialized: {host}:{port}")
    
    @classmethod
    def get_instance(cls) -> ServerConfig:
        """Get the global server configuration instance"""
        with cls._lock:
            if cls._instance is None:
                # Return default config if not initialized
                cls._instance = ServerConfig()
            return cls._instance
    
    @classmethod
    def get_port(cls) -> Optional[int]:
        """Get the server port"""
        return cls.get_instance().port
    
    @classmethod
    def get_ws_url(cls) -> str:
        """Get the WebSocket URL"""
        return cls.get_instance().ws_url
    
    @classmethod
    def get_http_url(cls) -> str:
        """Get the HTTP URL"""
        return cls.get_instance().http_url
    
    @classmethod
    def is_initialized(cls) -> bool:
        """Check if config is initialized"""
        with cls._lock:
            return cls._instance is not None and cls._instance.port is not None
    
    @classmethod
    def set_running(cls, is_running: bool):
        """Update running status"""
        with cls._lock:
            if cls._instance:
                cls._instance.is_running = is_running
    
    @classmethod
    def get_info(cls) -> dict:
        """Get all server information as dictionary"""
        return cls.get_instance().to_dict()


# Convenience functions for global access
def get_server_port() -> Optional[int]:
    """Get the current server port"""
    return GlobalServerConfig.get_port()


def get_server_config() -> ServerConfig:
    """Get the server configuration"""
    return GlobalServerConfig.get_instance()


def get_ws_url() -> str:
    """Get the WebSocket URL"""
    return GlobalServerConfig.get_ws_url()
