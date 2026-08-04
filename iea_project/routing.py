from django.urls import path
from . import consumers

websocket_urlpatterns = [
    path('ws/<str:app_name>/log/', consumers.ChatConsumer.as_asgi()),
]
