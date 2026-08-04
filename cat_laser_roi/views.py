from django.shortcuts import render
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
import json
import sys
import asyncio
import time
import logging
from logging.handlers import RotatingFileHandler
import os
from datetime import datetime

from channels.layers import get_channel_layer
from iea_project.consumers import LOG_HISTORY
from .forms import OptimizationForm
from .optimization_logic import get_or_calculate_patterns, solve_phase2, find_optimal_stock_length

# Configure logging với file storage
LOG_DIR = '/app/logs'
os.makedirs(LOG_DIR, exist_ok=True)

logger = logging.getLogger('cat_laser_roi')
logger.setLevel(logging.INFO)

# Console handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter('%(asctime)s [CAT_LASER_ROI] %(levelname)s: %(message)s'))
logger.addHandler(console_handler)

# File handler với rotation (10MB per file, giữ 5 files)
file_handler = RotatingFileHandler(
    os.path.join(LOG_DIR, 'cat_laser_roi.log'),
    maxBytes=10*1024*1024,  # 10MB
    backupCount=5,
    encoding='utf-8'
)
file_handler.setFormatter(logging.Formatter('%(asctime)s [CAT_LASER_ROI] %(levelname)s: %(message)s'))
logger.addHandler(file_handler)

class TeeStream:
    def __init__(self, websocket_room):
        self.websocket_room = websocket_room
        LOG_HISTORY[self.websocket_room] = []

    async def send_message_to_websocket(self, message):
        LOG_HISTORY[self.websocket_room].append(message)
        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            self.websocket_room,
            {"type": "chat.message", "message": message},
        )

    def write(self, message):
        if message.strip():
            asyncio.run(self.send_message_to_websocket(message))

    def flush(self):
        pass

@login_required
def index(request):
    form = OptimizationForm()
    context = {'form': form}
    return render(request, 'cat_laser_roi/index.html', context)

@login_required
def run_optimization(request):
    if request.method == 'POST':
        original_stdout = sys.stdout
        room_name = "log_gurobi_solver_cat_laser_roi"
        try:
            sys.stdout = TeeStream(room_name)
            
            # === LOGGING USER REQUEST ===
            logger.info("="*60)
            logger.info(f"NEW OPTIMIZATION REQUEST at {datetime.now().isoformat()}")
            logger.info(f"User: {request.user.username}")
            logger.info("="*60)
            
            data = json.loads(request.body)
            stock_length = data.get('stock_length')
            max_waste_percentage = float(data.get('max_waste_percentage', 1.0)) / 100  # Convert percentage to decimal
            max_surplus = data.get('max_surplus')
            max_total_surplus = data.get('max_total_surplus')  # NEW: Tổng tồn kho tối đa
            use_priority_constraint = data.get('use_priority_constraint')
            pattern_limit = data.get('pattern_limit', 100000)  # NEW: Giới hạn patterns cho mode bình thường
            optimize_stock_length = data.get('optimize_stock_length', False)
            optimize_min_length = data.get('optimize_min_length', 5000)  # NEW: Chiều dài tối thiểu
            optimize_max_length = data.get('optimize_max_length', 6000)  # NEW: Chiều dài tối đa
            optimize_search_step = data.get('optimize_search_step', 10)  # NEW: Bước nhảy tùy chỉnh
            optimize_stop_on_first = data.get('optimize_stop_on_first', False)  # NEW: Dừng ngay khi tìm thấy nghiệm
            trim_start = data.get('trim_start', 10)  # Tề đầu sắt (mm)
            # use_combined_mode = data.get('use_combined_mode')
            time_limit_minutes = data.get('time_limit_minutes')
            pieces_data = data.get('pieces_data')


            if not pieces_data:  # FIXED: Added check for empty pieces_data to prevent index errors downstream.
                print("❌ Không có dữ liệu đoạn cắt được cung cấp.<br>")
                return JsonResponse({'status': 'error', 'message': 'Không có dữ liệu đoạn cắt.'}, status=400)

            # Filter ra các hàng hợp lệ (có đủ cột tên, chiều dài, số lượng)
            valid_rows = [
                item for item in pieces_data 
                if item and len(item) >= 3 
                and item[0] is not None and item[0] != ''
                and item[1] is not None and item[1] != ''
                and item[2] is not None and item[2] != ''
            ]
            
            if not valid_rows:
                print("❌ Không có dữ liệu hợp lệ. Vui lòng kiểm tra lại bảng dữ liệu.<br>")
                return JsonResponse({'status': 'error', 'message': 'Không có dữ liệu đoạn cắt hợp lệ.'}, status=400)
            
            # Parse dữ liệu từ các hàng hợp lệ (New format: 4 columns without Priority)
            piece_names = [str(row[0]) for row in valid_rows]
            piece_lengths = [float(row[1]) for row in valid_rows]
            demands_list = [int(row[2]) for row in valid_rows]
            priorities_list = [0 for _ in valid_rows]  # Priority disabled, always 0
            is_doan_cuoi = [bool(row[3]) if len(row) > 3 and row[3] is not None else False for row in valid_rows]

            # === LOGGING INPUT PARAMETERS ===
            logger.info(f"Stock Length: {stock_length}mm")
            logger.info(f"Max Waste %: {max_waste_percentage*100:.2f}%")
            logger.info(f"Max Surplus per type: {max_surplus}")
            logger.info(f"Max Total Surplus: {max_total_surplus}")
            logger.info(f"Trim Start: {trim_start}mm")
            logger.info(f"Priority Constraint: {use_priority_constraint}")
            logger.info(f"Pattern Limit: {pattern_limit}")
            logger.info(f"Optimize Stock Length: {optimize_stock_length}")
            logger.info(f"Time Limit: {time_limit_minutes} minutes")
            logger.info(f"Number of piece types: {len(piece_names)}")
            for i, (name, length, demand, priority, is_end) in enumerate(zip(piece_names, piece_lengths, demands_list, priorities_list, is_doan_cuoi)):
                logger.info(f"  [{i+1}] {name}: {length}mm x {demand} pcs (priority={priority}, is_end={is_end})")
            logger.info("-"*60)

            # Nếu bật tính năng tối ưu chiều dài cây sắt
            if optimize_stock_length:
                logger.info("Starting OPTIMAL STOCK LENGTH SEARCH...")
                logger.info(f"Search range: {optimize_min_length}mm - {optimize_max_length}mm (step={optimize_search_step})")
                optimal_length, optimal_waste_pct, best_result = find_optimal_stock_length(
                    piece_names=piece_names,
                    piece_lengths=piece_lengths,
                    demands_list=demands_list,
                    priorities_list=priorities_list,
                    is_doan_cuoi=is_doan_cuoi,
                    max_surplus=max_surplus,
                    use_priority_constraint=use_priority_constraint,
                    time_limit_seconds=time_limit_minutes * 60,
                    kerf_width=1,
                    max_waste_percentage=max_waste_percentage,
                    min_length=optimize_min_length,
                    max_length=optimize_max_length,
                    step=optimize_search_step,  # Sử dụng giá trị từ form
                    trim_start=trim_start,
                    doan_thua_cat_tay=0,
                    max_total_surplus=max_total_surplus,
                    pattern_limit=pattern_limit,  # Dùng chung pattern_limit cho cả 2 mode
                    stop_on_first=optimize_stop_on_first  # Dừng ngay khi tìm thấy nghiệm
                )
                
                if optimal_length is None:
                    print("❌ Không tìm thấy chiều dài tối ưu trong khoảng cho phép.<br>")
                else:
                    print(f"<br>✅ Hoàn tất! Chiều dài tối ưu đã được tìm thấy: <b>{optimal_length}mm</b><br>")
                    print(f"<br><i>💡 Để tính kế hoạch cắt chi tiết, vui lòng bỏ tick checkbox và nhập chiều dài {optimal_length}mm vào trường 'Chiều dài cây sắt'.</i><br>")
                
                # KHÔNG chạy Phase 2 - chỉ hiển thị kết quả tìm kiếm
                return JsonResponse({'status': 'success', 'message': 'Optimal length search completed.'})

            
            # Chạy bình thường khi không dùng tìm kiếm tối ưu
            logger.info("Starting Phase 1: Pattern Generation (Normal Mode)...")
            patterns_data = get_or_calculate_patterns(
                stock_length, piece_lengths, 1, max_waste_percentage, trim_start, 0, pattern_limit=pattern_limit
            )
            
            if patterns_data is not None and not patterns_data.empty:
                logger.info(f"Phase 1 complete. Found {len(patterns_data)} patterns.")
                logger.info("Starting Phase 2: Distribution Optimization...")
                result = solve_phase2(
                    stock_length,
                    patterns_data,
                    piece_names,
                    piece_lengths,
                    demands_list,
                    priorities_list,
                    max_surplus,
                    use_priority_constraint=use_priority_constraint,
                    is_doan_cuoi=is_doan_cuoi,
                    time_limit_seconds=time_limit_minutes * 60,
                    optimal_stock_info=None  # Không có optimal info khi chạy bình thường
                )
                logger.info("Phase 2 complete.")
                
                # === LOG OPTIMIZATION RESULTS ===
                if result:
                    logger.info("="*60)
                    logger.info("OPTIMIZATION RESULTS")
                    logger.info(f"  Total Bars Used: {result['total_bars']}")
                    logger.info(f"  Total Waste: {result['total_waste_mm']:.2f}mm ({result['waste_percentage']:.2f}%)")
                    logger.info(f"  Total Surplus: {result['total_surplus']} pcs")
                    logger.info("="*60)
                else:
                    logger.warning("Optimization failed - no result returned")
            else:
                logger.warning("No patterns found from Phase 1!")

            logger.info("="*60)
            logger.info("OPTIMIZATION COMPLETE")
            logger.info("="*60)
            return JsonResponse({'status': 'success', 'message': 'Optimization process finished.'})

        except Exception as e:
            error_message = f"Đã xảy ra lỗi trong view: {e}"
            print(error_message)
            return JsonResponse({'status': 'error', 'message': error_message}, status=500)
        finally:
            sys.stdout = original_stdout
    return JsonResponse({'error': 'Invalid request method'}, status=400)