#!/usr/bin/env python
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'iea_project.settings')
sys.path.insert(0, '/app')
django.setup()

from django.contrib.auth.models import User

# Mật khẩu lấy từ biến môi trường — KHÔNG ghi cứng trong code vì repo này công khai.
# Dùng:  USER1_PASSWORD='matkhau' python create_user.py
USER1_PASSWORD = os.environ.get('USER1_PASSWORD')
if not USER1_PASSWORD:
    sys.exit("Thiếu biến môi trường USER1_PASSWORD. VD: USER1_PASSWORD='...' python create_user.py")

# Tạo user mới (không phải staff/superuser)
if not User.objects.filter(username='user1').exists():
    user = User.objects.create_user(username='user1', password=USER1_PASSWORD)
    user.is_staff = False
    user.is_superuser = False
    user.save()
    print('Created user: user1')
else:
    print('User user1 already exists')

# Đảm bảo admin có quyền staff và superuser
admin_user = User.objects.get(username='admin')
admin_user.is_staff = True
admin_user.is_superuser = True
admin_user.save()
print('Admin permissions confirmed')

# Liệt kê tất cả users
print()
print('--- All Users ---')
for u in User.objects.all():
    print(f'{u.username}: staff={u.is_staff}, superuser={u.is_superuser}')
