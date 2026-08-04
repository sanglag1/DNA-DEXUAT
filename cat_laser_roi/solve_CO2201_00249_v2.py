"""
GIẢI BÀI TOÁN CO-2201-00249 - PHIÊN BẢN HOÀN CHÍNH
Gộp các đoạn cùng chiều dài trước khi tối ưu
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from ortools.sat.python import cp_model
import pandas as pd

# ===================================================================
# DATA GỐC TỪ CO-2201-00249
# ===================================================================
RAW_DATA = [
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
# GỘP CÁC ĐOẠN CÙNG CHIỀU DÀI
# ===================================================================
def merge_by_length(raw_data):
    """Gộp các đoạn có cùng chiều dài"""
    merged = {}
    for stt, ma, ten, dai, sl in raw_data:
        if dai not in merged:
            merged[dai] = {
                'length': dai,
                'total_qty': 0,
                'items': []
            }
        merged[dai]['total_qty'] += sl
        merged[dai]['items'].append((ma, ten, sl))
    
    # Sắp xếp theo chiều dài giảm dần
    sorted_merged = sorted(merged.values(), key=lambda x: -x['length'])
    return sorted_merged

# ===================================================================
# THAM SỐ
# ===================================================================
STOCK_LENGTH = 9000
KERF_WIDTH = 1
TRIM_START = 10
MAX_WASTE_PCT = 0.15  # 15%
MAX_SURPLUS = 300
TIME_LIMIT = 300

# ===================================================================
# PHASE 1: TÌM PATTERNS
# ===================================================================
def find_patterns(stock_length, piece_lengths, kerf_width, max_waste_pct, trim_start, limit=200000):
    print(f"\n🔍 PHASE 1: Tìm patterns")
    print(f"   Stock length: {stock_length}mm")
    print(f"   Max waste: {max_waste_pct*100:.0f}%")
    print(f"   Số loại đoạn: {len(piece_lengths)}")
    
    model = cp_model.CpModel()
    num_pieces = len(piece_lengths)
    
    # Biến: số lượng mỗi loại đoạn trong 1 pattern
    counts = [model.NewIntVar(0, 50, f'seg_{i}') for i in range(num_pieces)]
    
    # Tổng chiều dài sử dụng
    total_length = sum(counts[i] * piece_lengths[i] for i in range(num_pieces))
    total_kerf = sum(counts) * kerf_width
    total_used = total_length + total_kerf + trim_start
    
    # Ràng buộc
    model.Add(total_used <= stock_length)
    min_used = int(stock_length * (1 - max_waste_pct))
    model.Add(total_used >= min_used)
    
    class SolutionCollector(cp_model.CpSolverSolutionCallback):
        def __init__(self, variables, limit):
            cp_model.CpSolverSolutionCallback.__init__(self)
            self.variables = variables
            self.limit = limit
            self.solutions = set()
        
        def on_solution_callback(self):
            if len(self.solutions) >= self.limit:
                self.StopSearch()
                return
            solution = tuple(self.Value(v) for v in self.variables)
            if sum(solution) > 0:
                self.solutions.add(solution)
    
    solver = cp_model.CpSolver()
    solver.parameters.enumerate_all_solutions = True
    collector = SolutionCollector(counts, limit)
    
    print(f"   Đang tìm kiếm (tối đa {limit:,} patterns)...")
    status = solver.Solve(model, collector)
    
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        patterns = list(collector.solutions)
        
        # Tính hao hụt
        patterns_with_waste = []
        for p in patterns:
            used = sum(p[i] * piece_lengths[i] for i in range(num_pieces))
            used += sum(p) * kerf_width + trim_start
            waste = stock_length - used
            patterns_with_waste.append(list(p) + [waste])
        
        # Sắp xếp theo hao hụt
        patterns_with_waste.sort(key=lambda x: x[-1])
        
        print(f"   ✅ Tìm được {len(patterns_with_waste):,} patterns")
        
        # Kiểm tra coverage
        print(f"\n📋 Kiểm tra coverage:")
        for i, length in enumerate(piece_lengths):
            max_qty = max(p[i] for p in patterns_with_waste)
            count = sum(1 for p in patterns_with_waste if p[i] > 0)
            status = "✅" if count > 0 else "❌"
            print(f"   {status} {length}mm: max {max_qty}/pattern, có trong {count:,} patterns")
        
        return patterns_with_waste
    else:
        print("   ❌ Không tìm được pattern!")
        return []

# ===================================================================
# PHASE 2: PHÂN BỔ
# ===================================================================
def solve_distribution(patterns, piece_lengths, demands, max_surplus, time_limit):
    print(f"\n🔧 PHASE 2: Phân bổ patterns")
    print(f"   Số patterns: {len(patterns):,}")
    print(f"   Số loại đoạn: {len(demands)}")
    print(f"   Max surplus/loại: {max_surplus}")
    
    model = cp_model.CpModel()
    num_patterns = len(patterns)
    num_pieces = len(piece_lengths)
    
    # Biến: số lần dùng mỗi pattern
    max_bars = sum(demands) // 2  # Ước lượng max
    x = [model.NewIntVar(0, max_bars, f'x_{j}') for j in range(num_patterns)]
    
    # Ràng buộc: đáp ứng nhu cầu
    surplus_vars = []
    for i in range(num_pieces):
        produced = sum(x[j] * patterns[j][i] for j in range(num_patterns))
        model.Add(produced >= demands[i])
        
        surplus = model.NewIntVar(0, max_bars * 10, f'surplus_{i}')
        model.Add(surplus == produced - demands[i])
        model.Add(surplus <= max_surplus)
        surplus_vars.append(surplus)
    
    # Mục tiêu: tối thiểu hao hụt
    total_waste = sum(x[j] * patterns[j][-1] for j in range(num_patterns))
    model.Minimize(total_waste)
    
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    
    print(f"   Đang giải (timeout: {time_limit}s)...")
    status = solver.Solve(model)
    
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        print(f"   ✅ Tìm được nghiệm! Status: {solver.StatusName(status)}")
        
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
                result['patterns_used'].append({
                    'pattern': pattern[:-1],
                    'count': count,
                    'waste_mm': pattern[-1]
                })
                result['total_bars'] += count
                result['total_waste'] += count * pattern[-1]
                
                for i in range(num_pieces):
                    result['production'][i] += count * pattern[i]
        
        for i in range(num_pieces):
            result['surplus'][i] = result['production'][i] - demands[i]
        
        return result
    else:
        print(f"   ❌ Không tìm được nghiệm! Status: {solver.StatusName(status)}")
        return None

# ===================================================================
# MAIN
# ===================================================================
if __name__ == "__main__":
    print("=" * 70)
    print("GIẢI BÀI TOÁN CẮT SẮT CO-2201-00249")
    print("=" * 70)
    
    # Gộp các đoạn cùng chiều dài
    merged_data = merge_by_length(RAW_DATA)
    
    print(f"\n📊 DỮ LIỆU SAU KHI GỘP:")
    print(f"   Số chiều dài khác nhau: {len(merged_data)}")
    print()
    
    piece_lengths = [m['length'] for m in merged_data]
    demands = [m['total_qty'] for m in merged_data]
    
    for i, m in enumerate(merged_data):
        items_str = ", ".join([f"{it[0]}×{it[2]}" for it in m['items']])
        print(f"   {i+1}. {m['length']}mm: Tổng {m['total_qty']} ({items_str})")
    
    print(f"\n   Tổng số lượng: {sum(demands):,}")
    
    # Phase 1
    patterns = find_patterns(STOCK_LENGTH, piece_lengths, KERF_WIDTH, MAX_WASTE_PCT, TRIM_START)
    
    if not patterns:
        print("\n❌ THẤT BẠI ở Phase 1!")
        sys.exit(1)
    
    # Phase 2
    result = solve_distribution(patterns, piece_lengths, demands, MAX_SURPLUS, TIME_LIMIT)
    
    if result:
        print("\n" + "=" * 70)
        print("KẾT QUẢ TỐI ƯU")
        print("=" * 70)
        
        waste_pct = (result['total_waste'] / (result['total_bars'] * STOCK_LENGTH)) * 100
        
        print(f"\n📦 TỔNG KẾT:")
        print(f"   Tổng số cây sắt: {result['total_bars']} cây")
        print(f"   Tổng chiều dài: {result['total_bars'] * STOCK_LENGTH / 1000:.1f}m")
        print(f"   Tổng hao hụt: {result['total_waste'] / 1000:.2f}m ({waste_pct:.2f}%)")
        print(f"   Tổng tồn kho: {sum(result['surplus'])} đoạn")
        
        print(f"\n📊 CHI TIẾT TỪNG CHIỀU DÀI (SAU GỘP):")
        print("-" * 60)
        print(f"{'Dài':>8} | {'Cần':>8} | {'Cắt':>8} | {'Tồn':>6} | Chi tiết")
        print("-" * 60)
        for i, m in enumerate(merged_data):
            cat = result['production'][i]
            ton = result['surplus'][i]
            items = ", ".join([f"{it[0]}" for it in m['items']])
            print(f"{m['length']:>6}mm | {m['total_qty']:>8} | {cat:>8} | {ton:>6} | {items}")
        print("-" * 60)
        
        print(f"\n🔧 KẾ HOẠCH CẮT ({len(result['patterns_used'])} loại pattern):")
        print("-" * 70)
        
        for idx, pu in enumerate(result['patterns_used'], 1):
            pattern = pu['pattern']
            count = pu['count']
            waste = pu['waste_mm']
            
            segments = []
            for i, qty in enumerate(pattern):
                if qty > 0:
                    segments.append(f"{merged_data[i]['length']}mm×{qty}")
            
            print(f"Pattern {idx:>2}: {', '.join(segments):<45} | Hao hụt {waste:>4}mm | ×{count:>3} cây")
        
        print("-" * 70)
        
        # Lưu kết quả
        output_file = os.path.join(os.path.dirname(__file__), "docs", "KET_QUA_CO-2201-00249.txt")
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("=" * 60 + "\n")
            f.write("KẾT QUẢ TỐI ƯU CẮT SẮT CO-2201-00249\n")
            f.write("=" * 60 + "\n\n")
            f.write(f"Chiều dài cây sắt: {STOCK_LENGTH}mm\n")
            f.write(f"Tổng số cây sắt: {result['total_bars']} cây\n")
            f.write(f"Tổng hao hụt: {result['total_waste'] / 1000:.2f}m ({waste_pct:.2f}%)\n")
            f.write(f"Tổng tồn kho: {sum(result['surplus'])} đoạn\n\n")
            
            f.write("CHI TIẾT TỪNG CHIỀU DÀI:\n")
            f.write("-" * 60 + "\n")
            for i, m in enumerate(merged_data):
                cat = result['production'][i]
                ton = result['surplus'][i]
                f.write(f"{m['length']}mm: Cần {m['total_qty']}, Cắt {cat}, Tồn {ton}\n")
                for it in m['items']:
                    f.write(f"   - {it[0]} ({it[1]}): {it[2]}\n")
            
            f.write("\nKẾ HOẠCH CẮT:\n")
            f.write("-" * 60 + "\n")
            for idx, pu in enumerate(result['patterns_used'], 1):
                pattern = pu['pattern']
                count = pu['count']
                waste = pu['waste_mm']
                segments = ", ".join([f"{merged_data[i]['length']}mm×{pattern[i]}" for i in range(len(pattern)) if pattern[i] > 0])
                f.write(f"Pattern {idx}: {segments} | Hao hụt {waste}mm | ×{count} cây\n")
        
        print(f"\n💾 Đã lưu kết quả vào: {output_file}")
        
    else:
        print("\n❌ THẤT BẠI!")
