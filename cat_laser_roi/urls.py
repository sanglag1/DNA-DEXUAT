# cat_laser_roi/urls.py
from django.urls import path
from . import views

app_name = 'cat_laser_roi'

urlpatterns = [
    path('', views.index, name='index'),
    path('run_optimization/', views.run_optimization, name='run_optimization'),
]