# cat_laser/urls.py
from django.urls import path
from . import views

app_name = 'cat_laser'

urlpatterns = [
    path('', views.index, name='index'),
    path('optimize', views.optimize, name='optimize_laser'), # Root of the app shows the form
]