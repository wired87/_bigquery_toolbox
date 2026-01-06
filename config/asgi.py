import os
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
import dj.routing

# Start RELAY environment scanner on server startup
try:
    from validator import ToolRegistry
    ToolRegistry.start_env_scanner()
    print("✅ RELAY Environment Scanner started")
except Exception as e:
    print(f"⚠️  Could not start RELAY scanner: {e}")

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter(
            dj.routing.websocket_urlpatterns
        )
    ),
})
