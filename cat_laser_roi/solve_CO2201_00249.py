"""
GIẢI BÀI TOÁN CO-2201-00249
Script này sẽ tự động giải bài toán cắt sắt với các tham số tối ưu
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from ortools.sat.python import cp_model
import pandas as pd
import numpy as np

# ===================================================================
# DATA TỪ CO-2201-00249
# ===================================================================
DATA = [
    # (STT, Mã mảnh, Tên đoạn, Chiều dài mm, Số lượng)
    (1, "PHOI-I3.1.1", "V15 (1 tán)", 425, 100),
    (2, "PHOI-I3.1.2", "V15 (2 tán)", 420, 300),
    (3, "PHOI-I3.1.4", "V15 (1 dập)", 445, 200),
    (4, "PHOI-I3.1.4", "V15 (2 dập)", 400, 200),
    (5, "PHOI-I3.1.4", "V15 (1 dập)", 175, 200),
    (6, "PHOI-I3.2.1", "V15 (2 dập)", 367, 50),
    (7, "PHOI-I3.2.1", "V15", 367, 50),
    (8, "PHOI-I3.2.2", "V15", 324, 200),
    (9, "PHOI-I3.2.2", "V15 (4 dập)", 330, 200),
    (10, "PHOI-I3.2.3", "V15 (2 tán)", 367, 200),
    (11, "PHOI-I3.2.3", "V15", 397, 200),
    (12, "PHOI-I5.1.1", "V15", 850, 100),
    (13, "PHOI-I5.1.2", "V15", 420, 600),
    (14, "PHOI-I5.1.4", "V15", 870, 200),
    (15, "PHOI-I5.1.4", "V15", 400, 700),
    (16, "PHOI-I5.1.4", "V15", 175, 600),
    (17, "PHOI-I5.2.1", "V15", 425, 200),
    (18, "PHOI-I5.2.4", "V15", 445, 400),
    (19, "PHOI-I5.3.1", "V15", 365, 200),
    (20, "PHOI-I5.3.1", "V15", 405, 100),
    (21, "PHOI-I5.3.1", "V15", 375, 100),
    (22, "PHOI-I5.3.2", "V15", 665, 200),
    (23, "PHOI-I5.3.2", "V15", 145, 400),
]

# ===================================================================
# THAM SỐ TỐI ƯU
# ===================================================================
STOCK_LENGTH = 9000  # mm
KERF_WIDTH = 1       # mm (độ rộng lưỡi cắt)
TRIM_START = 10      # mm (phần tề đầu)
MAX_WASTE_PCT = 0.15 # 15% - nới lỏng để có nhiều patterns
MAX_SURPLUS = 500    # Tồn kho tối đa mỗi loại
TIME_LIMIT = 300     # 5 phút

# ===================================================================
# GIAI ĐOẠN 1: TÌM CÁC PATTERNS
# ===================================================================
def find_patterns(stock_length, piece_lengths, kerf_width, max_waste_pct, trim_start, limit=100000):
    """Tìm tất cả các phương án cắt khả thi"""
    print(f"🔍 Phase 1: Tìm patterns với stock={stock_length}mm, max_waste={max_waste_pct*100:.0f}%")
    
    model = cp_model.CpModel()
    num_pieces = len(piece_lengths)
    
    # Biến: số lượng mỗi loại đoạn trong pattern
    counts = [model.NewIntVar(0, 50, f'seg_{i}') for i in range(num_pieces)]
    
    # Tổng chiều dài sử dụng
    total_length = sum(counts[i] * piece_lengths[i] for i in range(num_pieces))
    total_kerf = sum(counts) * kerf_width
    total_used = total_length + total_kerf + trim_start
    
    # Ràng buộc: không vượt quá chiều dài cây sắt
    model.Add(total_used <= stock_length)
    
    # Ràng buộc: phải sử dụng ít nhất (1 - max_waste)% cây sắt
    min_used = int(stock_length * (1 - max_waste_pct))
    model.Add(total_used >= min_used)
    
    # Thu thập các nghiệm
    class SolutionCollector(cp_model.CpSolverSolutionCallback):
        def __init__(self, variables, limit):
            cp_model.CpSolverSolutionCallback.__init__(self)
            self.variables = variables
            self.limit = limit
            self.solutions = []
        
        def on_solution_callback(self):
            if len(self.solutions) >= self.limit:
                self.StopSearch()
                return
            solution = tuple(self.Value(v) for v in self.variables)
            if sum(solution) > 0:  # Phải có ít nhất 1 đoạn
                self.solutions.append(solution)
    
    solver = cp_model.CpSolver()
    solver.parameters.enumerate_all_solutions = True
    collector = SolutionCollector(counts, limit)
    
    status = solver.Solve(model, collector)
    
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        # Loại bỏ trùng lặp
        unique_patterns = list(set(collector.solutions))
        
        # Tính hao hụt cho mỗi pattern
        patterns_with_waste = []
        for p in unique_patterns:
            used = sum(p[i] * piece_lengths[i] for i in range(num_pieces))
            used += sum(p) * kerf_width + trim_start
            waste = stock_length - used
            patterns_with_waste.append((*p, waste))
        
        # Sắp xếp theo hao hụt tăng dần
        patterns_with_waste.sort(key=lambda x: x[-1])
        
        print(f"✅ Tìm được {len(patterns_with_waste):,} patterns")
        return patterns_with_waste
    else:
        print("❌ Không tìm được pattern nào!")
        return []

# ===================================================================
# GIAI ĐOẠN 2: PHÂN BỔ PATTERNS
# ===================================================================
def solve_distribution(patterns, piece_lengths, demands, max_surplus, time_limit):
    """Tìm số lần sử dụng mỗi pattern để đáp ứng nhu cầu"""
    print(f"\n🔧 Phase 2: Phân bổ {len(patterns):,} patterns cho {len(demands)} loại đoạn")
    
    model = cp_model.CpModel()
    num_patterns = len(patterns)
    num_pieces = len(piece_lengths)
    
    # Biến: số lần sử dụng mỗi pattern
    x = [model.NewIntVar(0, sum(demands), f'x_{j}') for j in range(num_patterns)]
    
    # Ràng buộc: đáp ứng nhu cầu mỗi loại đoạn
    surplus_vars = []
    for i in range(num_pieces):
        # Tổng sản lượng loại i từ tất cả patterns
        produced = sum(x[j] * patterns[j][i] for j in range(num_patterns))
        
        # Phải >= nhu cầu
        model.Add(produced >= demands[i])
        
        # Tồn kho = sản xuất - nhu cầu
        surplus = model.NewIntVar(0, sum(demands), f'surplus_{i}')
        model.Add(surplus == produced - demands[i])
        model.Add(surplus <= max_surplus)
        surplus_vars.append(surplus)
    
    # Mục tiêu: tối thiểu hóa tổng hao hụt (waste ở vị trí cuối của pattern)
    total_waste = sum(x[j] * patterns[j][-1] for j in range(num_patterns))
    model.Minimize(total_waste)
    
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    
    print("⏳ Đang giải Phase 2 (tối thiểu hao hụt)...")
    status = solver.Solve(model)
    
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        print("✅ Phase 2 thành công!")
        
        # Thu thập kết quả
        result = {
            'patterns_used': [],
            'total_bars': 0,
            'total_waste': 0,
            'production': [0] * num_pieces,
            'surplus': [0] * num_pieces
        }
        
        for j in range(num_patterns):
            count = solver.Value(x[j])
            if count > 0:
                pattern = patterns[j]
                waste = pattern[-1]
                result['patterns_used'].append({
                    'pattern': pattern[:-1],
                    'count': count,
                    'waste_mm': waste
                })
                result['total_bars'] += count
                result['total_waste'] += count * waste
                
                for i in range(num_pieces):
                    result['production'][i] += count * pattern[i]
        
        for i in range(num_pieces):
            result['surplus'][i] = result['production'][i] - demands[i]
        
        return result
    else:
        print(f"❌ Phase 2 thất bại! Status: {solver.StatusName(status)}")
        return None

# ===================================================================
# MAIN
# ===================================================================
if __name__ == "__main__":
    print("=" * 70)
    print("GIẢI BÀI TOÁN CẮT SẮT CO-2201-00249")
    print("=" * 70)
    
    # Chuẩn bị dữ liệu - KHÔNG gộp các đoạn cùng chiều dài
    # vì mỗi dòng có ý nghĩa riêng (khác nhau về dập, tán)
    piece_info = [(d[1], d[2], d[3], d[4]) for d in DATA]  # (mã, tên, dài, SL)
    piece_lengths = [d[3] for d in DATA]
    demands = [d[4] for d in DATA]
    
    print(f"\n📊 THỐNG KÊ:")
    print(f"   Số loại đoạn: {len(piece_lengths)}")
    print(f"   Tổng số lượng: {sum(demands):,}")
    print(f"   Đoạn ngắn nhất: {min(piece_lengths)}mm")
    print(f"   Đoạn dài nhất: {max(piece_lengths)}mm")
    print(f"   Chiều dài cây sắt: {STOCK_LENGTH}mm")
    print(f"   Hao hụt tối đa: {MAX_WASTE_PCT*100:.0f}%")
    print()
    
    # Phase 1: Tìm patterns
    patterns = find_patterns(
        STOCK_LENGTH, piece_lengths, KERF_WIDTH, 
        MAX_WASTE_PCT, TRIM_START, limit=200000
    )
    
    if not patterns:
        print("\n❌ THẤT BẠI: Không tìm được patterns phù hợp!")
        print("💡 Đề xuất: Thử tăng MAX_WASTE_PCT lên 20% hoặc chia nhỏ đơn hàng")
        sys.exit(1)
    
    # Kiểm tra coverage
    print("\n📋 Kiểm tra từng loại đoạn:")
    all_covered = True
    for i, length in enumerate(piece_lengths):
        has_pattern = any(p[i] > 0 for p in patterns)
        max_qty = max(p[i] for p in patterns)
        status = "✅" if has_pattern else "❌"
        print(f"   {status} {DATA[i][1]} ({length}mm): max {max_qty} đoạn/pattern")
        if not has_pattern:
            all_covered = False
    
    if not all_covered:
        print("\n❌ MỘT SỐ ĐOẠN KHÔNG CÓ TRONG PATTERNS!")
        sys.exit(1)
    
    # Phase 2: Phân bổ
    result = solve_distribution(patterns, piece_lengths, demands, MAX_SURPLUS, TIME_LIMIT)
    
    if result:
        print("\n" + "=" * 70)
        print("KẾT QUẢ TỐI ƯU")
        print("=" * 70)
        
        print(f"\n📦 TỔNG KẾT:")
        print(f"   Tổng số cây sắt: {result['total_bars']} cây")
        print(f"   Tổng chiều dài: {result['total_bars'] * STOCK_LENGTH / 1000:.1f}m")
        print(f"   Tổng hao hụt: {result['total_waste'] / 1000:.2f}m")
        waste_pct = (result['total_waste'] / (result['total_bars'] * STOCK_LENGTH)) * 100
        print(f"   % Hao hụt: {waste_pct:.2f}%")
        print(f"   Tổng tồn kho: {sum(result['surplus'])} đoạn")
        
        print(f"\n📊 CHI TIẾT TỪNG LOẠI ĐOẠN:")
        print("-" * 70)
        print(f"{'STT':>3} | {'Mã mảnh':<15} | {'Dài':>6} | {'Cần':>6} | {'Cắt':>6} | {'Tồn':>5}")
        print("-" * 70)
        for i, (stt, ma, ten, dai, can) in enumerate(DATA):
            cat = result['production'][i]
            ton = result['surplus'][i]
            print(f"{stt:>3} | {ma:<15} | {dai:>5}mm | {can:>6} | {cat:>6} | {ton:>5}")
        print("-" * 70)
        
        print(f"\n🔧 KẾ HOẠCH CẮT CHI TIẾT ({len(result['patterns_used'])} loại pattern):")
        print("-" * 70)
        
        # Tạo header
        header = "STT | "
        for i, (stt, ma, ten, dai, can) in enumerate(DATA):
            header += f"{dai}mm "
        header += "| Hao hụt | SL Cây"
        print(header)
        print("-" * 70)
        
        for idx, pu in enumerate(result['patterns_used'], 1):
            pattern = pu['pattern']
            count = pu['count']
            waste = pu['waste_mm']
            
            row = f"{idx:>3} | "
            for qty in pattern:
                if qty > 0:
                    row += f"{qty:>4} "
                else:
                    row += "   - "
            row += f"| {waste:>6}mm | {count:>5}"
            print(row)
        
        print("-" * 70)
        
        # Lưu kết quả ra file
        output_file = os.path.join(os.path.dirname(__file__), "docs", "KET_QUA_CO-2201-00249.txt")
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("KẾT QUẢ TỐI ƯU CẮT SẮT CO-2201-00249\n")
            f.write("=" * 50 + "\n\n")
            f.write(f"Chiều dài cây sắt: {STOCK_LENGTH}mm\n")
            f.write(f"Tổng số cây sắt: {result['total_bars']} cây\n")
            f.write(f"Tổng hao hụt: {result['total_waste'] / 1000:.2f}m ({waste_pct:.2f}%)\n")
            f.write(f"Tổng tồn kho: {sum(result['surplus'])} đoạn\n\n")
            
            f.write("CHI TIẾT TỪNG LOẠI ĐOẠN:\n")
            f.write("-" * 50 + "\n")
            for i, (stt, ma, ten, dai, can) in enumerate(DATA):
                cat = result['production'][i]
                ton = result['surplus'][i]
                f.write(f"{stt:>2}. {ma} ({dai}mm): Cần {can}, Cắt {cat}, Tồn {ton}\n")
            
            f.write("\nKẾ HOẠCH CẮT:\n")
            f.write("-" * 50 + "\n")
            for idx, pu in enumerate(result['patterns_used'], 1):
                pattern = pu['pattern']
                count = pu['count']
                waste = pu['waste_mm']
                segments = ", ".join([f"{DATA[i][3]}mm×{pattern[i]}" for i in range(len(pattern)) if pattern[i] > 0])
                f.write(f"Pattern {idx}: {segments} | Hao hụt {waste}mm | x{count} cây\n")
        
        print(f"\n💾 Đã lưu kết quả vào: {output_file}")
    else:
        print("\n❌ THẤT BẠI: Không thể tìm phương án phân bổ!")
        print("💡 Đề xuất:")
        print("   1. Chia đơn hàng thành 2 lô (I3 và I5) và chạy riêng")
        print("   2. Tăng MAX_SURPLUS lên 1000+")
        print("   3. Tăng MAX_WASTE_PCT lên 20%")
