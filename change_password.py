#!/usr/bin/env python
import os
import sys
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'iea_project.settings')

import django
django.setup()

from django.contrib.auth.models import User

try:
    user = User.objects.get(username='admin')
    user.set_password('CatsatIEA!')
    user.save()
    print("Password changed to CatsatIEA!")
except User.DoesNotExist:
    print("User 'admin' not found")
    sys.exit(1)
