from django.contrib import admin
from .models import OptimizationLog

@admin.register(OptimizationLog)
class OptimizationLogAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'user', 'module', 'status', 'duration_seconds']
    list_filter = ['module', 'status', 'user', 'created_at']
    readonly_fields = ['user', 'module', 'created_at', 'duration_seconds', 'input_data', 'parameters', 'output_summary', 'status', 'error_message']
    ordering = ['-created_at']
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
