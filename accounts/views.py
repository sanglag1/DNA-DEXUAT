from django.contrib.auth import authenticate, login, logout
from django.shortcuts import render, redirect
from django.http import JsonResponse
from .models import OTPCode
import json


def login_view(request):
    """Custom login view với 2-step TOTP support"""
    if request.user.is_authenticated:
        return redirect('cat_sat:index')
    
    error_message = None
    
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        
        # Authenticate user
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            # Check if user requires OTP
            try:
                otp_setting = OTPCode.objects.get(user=user)
                if otp_setting.is_active:
                    # OTP is required - store user info in session for step 2
                    request.session['pending_user_id'] = user.id
                    request.session['pending_username'] = user.username
                    return render(request, 'accounts/login.html', {
                        'show_otp_modal': True,
                        'pending_username': user.username
                    })
                else:
                    # OTP is disabled for this user
                    login(request, user)
                    return redirect('cat_sat:index')
            except OTPCode.DoesNotExist:
                # No OTP required for this user
                login(request, user)
                return redirect('cat_sat:index')
        else:
            error_message = 'Tên đăng nhập hoặc mật khẩu không đúng!'
    
    return render(request, 'accounts/login.html', {'error_message': error_message})


def verify_otp_view(request):
    """AJAX endpoint to verify OTP code"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            otp_code = data.get('otp_code', '').strip()
        except:
            otp_code = request.POST.get('otp_code', '').strip()
        
        user_id = request.session.get('pending_user_id')
        
        if not user_id:
            return JsonResponse({'success': False, 'error': 'Phiên đăng nhập đã hết hạn'})
        
        from django.contrib.auth.models import User
        try:
            user = User.objects.get(pk=user_id)
            otp_setting = OTPCode.objects.get(user=user)
            
            if otp_setting.verify_otp(otp_code):
                # OTP correct - login user
                login(request, user)
                # Clear session data
                del request.session['pending_user_id']
                del request.session['pending_username']
                return JsonResponse({'success': True, 'redirect': '/'})
            else:
                return JsonResponse({'success': False, 'error': 'Mã xác thực không đúng hoặc đã hết hạn!'})
        except (User.DoesNotExist, OTPCode.DoesNotExist):
            return JsonResponse({'success': False, 'error': 'Lỗi hệ thống'})
    
    return JsonResponse({'success': False, 'error': 'Invalid request'})


def logout_view(request):
    logout(request)
    return redirect('accounts:login')
