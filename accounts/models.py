from django.db import models
from django.contrib.auth.models import User
import pyotp


class OTPCode(models.Model):
    """Mã OTP theo thời gian - Admin có thể đọc mã hiện tại cho user"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='otp_code')
    secret_key = models.CharField(max_length=32, blank=True, help_text='Secret key cho TOTP')
    is_active = models.BooleanField(default=True, help_text='Bật/tắt yêu cầu OTP')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Mã OTP'
        verbose_name_plural = 'Mã OTP'
    
    def save(self, *args, **kwargs):
        # Auto-generate secret key if not set
        if not self.secret_key:
            self.secret_key = pyotp.random_base32()
        super().save(*args, **kwargs)
    
    def get_current_otp(self):
        """Lấy mã OTP hiện tại (thay đổi mỗi 30 giây)"""
        totp = pyotp.TOTP(self.secret_key)
        return totp.now()
    
    def verify_otp(self, code):
        """Kiểm tra mã OTP có đúng không"""
        totp = pyotp.TOTP(self.secret_key)
        return totp.verify(code, valid_window=1)  # Allow 1 step tolerance
    
    def time_remaining(self):
        """Số giây còn lại trước khi mã thay đổi"""
        import time
        return 30 - int(time.time() % 30)
    
    def __str__(self):
        status = '✓ Bật' if self.is_active else '✗ Tắt'
        return f'{self.user.username} - {status}'
