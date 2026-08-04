# Bù migration còn thiếu: app optimization_logs có model nhưng chưa từng được tạo
# migration nào, nên trên database mới bảng không tồn tại. Database cũ chạy được vì
# bảng đã được tạo tay từ trước.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='OptimizationLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('module', models.CharField(choices=[('cat_sat', 'MC Tu Dong'), ('cat_laser_roi', 'MC Laser')], max_length=30)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('duration_seconds', models.FloatField(blank=True, null=True)),
                ('input_data', models.JSONField(default=dict)),
                ('parameters', models.JSONField(default=dict)),
                ('output_summary', models.JSONField(blank=True, default=dict)),
                ('status', models.CharField(choices=[('success', 'OK'), ('error', 'Error'), ('timeout', 'Timeout')], default='success', max_length=10)),
                ('error_message', models.TextField(blank=True, default='')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
