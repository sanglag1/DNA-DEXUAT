from django.contrib import admin
from django.contrib.sessions.models import Session
from django.contrib.auth.models import User
from django.utils import timezone
from django.utils.html import format_html
from .models import OTPCode


class SessionAdmin(admin.ModelAdmin):
    list_display = ['session_key_short', 'get_username', 'expire_date', 'is_active']
    list_filter = ['expire_date']
    search_fields = ['session_key']
    readonly_fields = ['session_key', 'session_data', 'expire_date', 'get_username', 'get_decoded_data']
    
    def session_key_short(self, obj):
        return obj.session_key[:20] + '...'
    session_key_short.short_description = 'Session Key'
    
    def get_username(self, obj):
        data = obj.get_decoded()
        user_id = data.get('_auth_user_id')
        if user_id:
            try:
                user = User.objects.get(pk=user_id)
                return user.username
            except User.DoesNotExist:
                return f'Unknown (ID: {user_id})'
        return 'Anonymous'
    get_username.short_description = 'User'
    
    def is_active(self, obj):
        return obj.expire_date > timezone.now()
    is_active.boolean = True
    is_active.short_description = 'Active'
    
    def get_decoded_data(self, obj):
        return str(obj.get_decoded())
    get_decoded_data.short_description = 'Decoded Data'


class OTPCodeAdmin(admin.ModelAdmin):
    list_display = ['user', 'current_otp_display', 'time_remaining_display', 'is_active']
    list_filter = ['is_active']
    search_fields = ['user__username']
    readonly_fields = ['secret_key', 'current_otp_display', 'time_remaining_display']
    
    def current_otp_display(self, obj):
        """Hiển thị mã OTP hiện tại với font lớn"""
        if obj.is_active:
            otp = obj.get_current_otp()
            return format_html(
                '<span style="font-size: 24px; font-weight: bold; color: #2563eb; '
                'background: #dbeafe; padding: 4px 12px; border-radius: 6px; '
                'letter-spacing: 0.15em;">{}</span>',
                otp
            )
        return format_html('<span style="color: #9ca3af;">Đã tắt</span>')
    current_otp_display.short_description = 'MÃ HIỆN TẠI'
    
    def time_remaining_display(self, obj):
        """Hiển thị thời gian còn lại"""
        if obj.is_active:
            remaining = obj.time_remaining()
            color = '#dc2626' if remaining <= 5 else '#16a34a'
            return format_html(
                '<span style="font-weight: bold; color: {};">{} giây</span>',
                color, remaining
            )
        return '-'
    time_remaining_display.short_description = 'Còn lại'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user')


# Register models
admin.site.register(Session, SessionAdmin)
admin.site.register(OTPCode, OTPCodeAdmin)
