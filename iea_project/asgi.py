"""
ASGI config for iea_project project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.1/howto/deployment/asgi/
"""

import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from iea_project.routing import websocket_urlpatterns

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'iea_project.settings')

# Tăng timeout cho các tác vụ optimization chạy lâu (30 phút = 1800 giây)
# Mặc định là 10 giây, quá ngắn cho Phase 2 với nhiều patterns
application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter(websocket_urlpatterns)
    ),
})

# Cấu hình timeout cho Daphne/ASGI server
# Set qua biến môi trường hoặc command line khi chạy server:
# daphne -t 1800 iea_project.asgi:application
