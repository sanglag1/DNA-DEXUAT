"""
API endpoints cho hệ thống tích hợp ERP.
Tất cả các endpoint đều stateless (không lưu dữ liệu) — ERP backend tự lưu.
"""
from django.urls import path
from . import views

app_name = 'api'

urlpatterns = [
    # Đề xuất thanh sắt: bung BOM + tối ưu chiều dài mua mỗi loại sắt
    path('v1/de_xuat/propose/', views.api_de_xuat_propose, name='de_xuat_propose'),
]
