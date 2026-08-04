#!/usr/bin/env python
"""
Script tạo OTP TOTP cho user ketoan
Chạy trong docker: docker exec catsat_web python setup_otp.py
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'iea_project.settings')
django.setup()

from django.contrib.auth.models import User
from accounts.models import OTPCode

# Get or create ketoan user
try:
    ketoan = User.objects.get(username='ketoan')
    print(f"Found user: {ketoan.username}")
except User.DoesNotExist:
    # Lấy từ biến môi trường, không ghi cứng vì repo này công khai.
    # Dùng:  KETOAN_PASSWORD='matkhau' python setup_otp.py
    ketoan = User.objects.create_user('ketoan', password=os.environ['KETOAN_PASSWORD'])
    ketoan.is_staff = False
    ketoan.is_superuser = False
    ketoan.save()
    print(f"Created user: ketoan")

# Create or update OTP for ketoan
otp, created = OTPCode.objects.get_or_create(user=ketoan)
otp.is_active = True
otp.save()

if created:
    print(f"OTP created for ketoan")
else:
    print(f"OTP enabled for ketoan")

print(f"Secret key: {otp.secret_key}")
print(f"Current OTP: {otp.get_current_otp()}")
