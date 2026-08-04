# Bù migration còn thiếu: model OTPCode đã đổi từ lưu mã tĩnh 'code' sang lưu
# 'secret_key' cho TOTP, nhưng migration tương ứng chưa từng được tạo. Database cũ
# vẫn chạy được vì đã sửa tay, còn database mới thì thiếu cột -> lỗi
# ProgrammingError: column accounts_otpcode.secret_key does not exist

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='otpcode',
            name='code',
        ),
        migrations.AddField(
            model_name='otpcode',
            name='secret_key',
            field=models.CharField(blank=True, help_text='Secret key cho TOTP', max_length=32),
        ),
    ]
