from django.urls import path
from . import views
from . import de_xuat_views  # Màn DEMO "Đề xuất thanh sắt" — độc lập, không đụng logic MCTĐ

app_name = 'cat_sat'  # This defines a namespace for the app's URLs

urlpatterns = [
    # This pattern is for your index view and is named 'index'
    path('', views.index, name='index'),
    path('optimize/', views.optimize, name='optimize'),
    path('export-excel-gd1/', views.export_excel_phase1, name='export_excel_phase1'),
    # Đề xuất thanh sắt (steel bar recommendation) — độc lập với MCTĐ/Laser
    path('de_xuat/', de_xuat_views.de_xuat_index, name='de_xuat_index'),
    path('de_xuat/materials/', de_xuat_views.de_xuat_materials, name='de_xuat_materials'),
    path('de_xuat/optimize_material/', de_xuat_views.de_xuat_optimize_material, name='de_xuat_optimize_material'),
]