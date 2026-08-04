# cat_laser/views.py
from django.shortcuts import render
from django.http import JsonResponse
# from django.views.decorators.csrf import csrf_exempt # Use carefully or handle CSRF properly
import json
import time
import sys 

from .forms import OptimizationLaserForm
from .optimization_logic import *
from .utils import do_day_luoi_cua
from .optimization_logic import generate_patterns, solve_patterns

# Use the same fixed group name as the consumer
SHARED_GROUP_NAME = "log_gurobi_solver_cat_laser"
tee_stream = TeeStream(SHARED_GROUP_NAME)

def index(request):
    form = OptimizationLaserForm()
    context = {'form': form}
    return render(request, 'cat_laser/index.html', context)

# @csrf_exempt # Simplifies testing; implement proper CSRF for production fetch POSTs
def optimize(request):
    if request.method == 'POST':
        try:
            sys.stdout = tee_stream
            sys.stderr = tee_stream
            # Assume JSON data from fetch
            data = json.loads(request.body)

            LENGTH = int(data['length'])
            KICH_THUOC_DOAN = list(map(float, data['segment_sizes']))
            SL_CAT = list(map(int, data['demands']))
            k_factors = do_day_luoi_cua(KICH_THUOC_DOAN, data['blade_width_mctd'])
            SO_LUONG_TON_KHO = int(data['max_stock_over'])     

            # KICH_THUOC_DOAN = [2360.8, 1684.8, 1289.2, 1162.2, 565, 46]
            # k_factors = [1, 1, 1, 1, 3, 3]
            # LENGTH = 5850
            # SL_CAT = [600, 1200, 1200, 600, 1200, 1200]
            # SO_LUONG_TON_KHO = 20

            print("Đang tìm các patterns cho 1 cây sắt...<br>")
            solutions = generate_patterns(KICH_THUOC_DOAN, k_factors, LENGTH)
            # print("!!!!", type(solutions).__name__, "<br>")

            print("Đang giải phương trình.....<br>")
            print("Vui lòng đợi tối đa 1 phút.....<br>")
            solve_patterns(solutions, LENGTH, KICH_THUOC_DOAN, SL_CAT, SO_LUONG_TON_KHO)


            return JsonResponse({
                "status": "success",
            }, status=200)
        except Exception as e:
            print(e)