import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from apps.notifications.routing import websocket_urlpatterns
from apps.notifications.middleware import JWTAuthMiddlewareStack

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_planner.settings')

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": JWTAuthMiddlewareStack(
        URLRouter(websocket_urlpatterns)
    ),
})
