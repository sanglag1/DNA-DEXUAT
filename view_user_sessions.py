#!/usr/bin/env python
"""
Script để xem sessions của một user cụ thể
Chạy: docker exec catsat_web python /app/view_user_sessions.py ketoan
"""
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'iea_project.settings')
sys.path.insert(0, '/app')
django.setup()

from django.contrib.sessions.models import Session
from django.contrib.auth.models import User
from django.utils import timezone

def view_user_sessions(username):
    """Xem sessions của một user cụ thể"""
    try:
        user = User.objects.get(username=username)
    except User.DoesNotExist:
        print(f"User '{username}' not found")
        return
    
    print(f"\n=== SESSIONS FOR USER: {username} ===")
    
    sessions = Session.objects.filter(expire_date__gte=timezone.now())
    user_sessions = []
    
    for session in sessions:
        data = session.get_decoded()
        if str(data.get('_auth_user_id')) == str(user.id):
            user_sessions.append({
                'session_key': session.session_key,
                'expire_date': session.expire_date,
                'data': data
            })
    
    if not user_sessions:
        print(f"No active sessions found for user '{username}'")
        return
    
    for i, s in enumerate(user_sessions, 1):
        print(f"\nSession {i}:")
        print(f"  Key: {s['session_key'][:25]}...")
        print(f"  Expires: {s['expire_date']}")
    
    print(f"\nTotal: {len(user_sessions)} active session(s)")

def clear_user_sessions(username):
    """Xóa tất cả sessions của một user (logout từ tất cả thiết bị)"""
    try:
        user = User.objects.get(username=username)
    except User.DoesNotExist:
        print(f"User '{username}' not found")
        return
    
    count = 0
    for session in Session.objects.filter(expire_date__gte=timezone.now()):
        data = session.get_decoded()
        if str(data.get('_auth_user_id')) == str(user.id):
            session.delete()
            count += 1
    
    print(f"Logged out user '{username}' from {count} device(s)")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python view_user_sessions.py <username>       # View sessions")
        print("  python view_user_sessions.py <username> clear # Logout from all devices")
        sys.exit(1)
    
    username = sys.argv[1]
    
    if len(sys.argv) > 2 and sys.argv[2] == 'clear':
        clear_user_sessions(username)
    else:
        view_user_sessions(username)
