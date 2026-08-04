from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from .models import OptimizationLog

@login_required
def history_view(request):
    logs = OptimizationLog.objects.select_related('user').all()[:100]
    module = request.GET.get('module')
    if module: logs = logs.filter(module=module)
    status = request.GET.get('status')
    if status: logs = logs.filter(status=status)
    return render(request, 'optimization_logs/history.html', {'logs': logs})
