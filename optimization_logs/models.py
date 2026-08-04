from django.db import models
from django.contrib.auth.models import User

class OptimizationLog(models.Model):
    STATUS_CHOICES = [('success', 'OK'), ('error', 'Error'), ('timeout', 'Timeout')]
    MODULE_CHOICES = [('cat_sat', 'MC Tu Dong'), ('cat_laser_roi', 'MC Laser')]

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    module = models.CharField(max_length=30, choices=MODULE_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    duration_seconds = models.FloatField(null=True, blank=True)
    input_data = models.JSONField(default=dict)
    parameters = models.JSONField(default=dict)
    output_summary = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='success')
    error_message = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_module_display()} - {self.user} - {self.created_at:%Y-%m-%d %H:%M}"
