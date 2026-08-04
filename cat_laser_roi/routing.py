from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/cat_laser_roi/log/$', consumers.LogConsumer.as_asgi()),
]