from django.urls import path
from . import views

app_name = 'optimization_logs'
urlpatterns = [
    path('', views.history_view, name='history'),
]
