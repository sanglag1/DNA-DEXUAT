#!/usr/bin/env python
"""
Script để xem và quản lý sessions trong Django
Chạy: docker exec catsat_web python /app/view_sessions.py
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

def list_sessions():
    """Liệt kê tất cả sessions đang hoạt động"""
    print("\n=== ACTIVE SESSIONS ===")
    sessions = Session.objects.filter(expire_date__gte=timezone.now())
    
    if not sessions.exists():
        print("No active sessions found.")
        return
    
    for session in sessions:
        data = session.get_decoded()
        user_id = data.get('_auth_user_id')
        
        if user_id:
            try:
                user = User.objects.get(pk=user_id)
                username = user.username
            except User.DoesNotExist:
                username = f"Unknown (ID: {user_id})"
        else:
            username = "Anonymous"
        
        print(f"  Session Key: {session.session_key[:20]}...")
        print(f"  User: {username}")
        print(f"  Expires: {session.expire_date}")
        print("  ---")
    
    print(f"\nTotal: {sessions.count()} active session(s)")

def clear_all_sessions():
    """Xóa tất cả sessions (log out tất cả users)"""
    count = Session.objects.all().delete()[0]
    print(f"Deleted {count} session(s)")

def clear_user_sessions(username):
    """Xóa sessions của một user cụ thể"""
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
    
    print(f"Deleted {count} session(s) for user '{username}'")

if __name__ == '__main__':
    if len(sys.argv) > 1:
        action = sys.argv[1]
        if action == 'clear_all':
            clear_all_sessions()
        elif action == 'clear_user' and len(sys.argv) > 2:
            clear_user_sessions(sys.argv[2])
        else:
            print("Usage:")
            print("  python view_sessions.py           # List all sessions")
            print("  python view_sessions.py clear_all # Clear all sessions")
            print("  python view_sessions.py clear_user <username> # Clear user sessions")
    else:
        list_sessions()
