"""
GIẢI BÀI TOÁN CO-2201-00249 - PHIÊN BẢN CUỐI CÙNG
Đảm bảo TẤT CẢ các loại đoạn đều có patterns bằng cách tạo patterns theo cách khác
"""
import os
import sys
from itertools import product
from ortools.sat.python import cp_model

# ===================================================================
# DATA
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
# GỘP DỮ LIỆU
# ===================================================================
def merge_by_length(raw_data):
    merged = {}
    for stt, ma, ten, dai, sl in raw_data:
        if dai not in merged:
            merged[dai] = {'length': dai, 'total_qty': 0, 'items': []}
        merged[dai]['total_qty'] += sl
        merged[dai]['items'].append((ma, ten, sl))
    return sorted(merged.values(), key=lambda x: -x['length'])

# ===================================================================
# TẠO PATTERNS BẰNG BRUTE FORCE (đảm bảo coverage)
# ===================================================================
def generate_patterns_bruteforce(stock_length, piece_lengths, kerf_width, trim_start, max_waste_pct):
    """
    Tạo patterns bằng cách duyệt tất cả tổ hợp có thể.
    Giới hạn max đoạn/loại để tránh quá nhiều tổ hợp.
    """
    print(f"\n🔍 Đang tạo patterns (brute-force)...")
    
    n = len(piece_lengths)
    min_used = int(stock_length * (1 - max_waste_pct))
    
    # Tính max số đoạn cho mỗi loại
    max_counts = []
    for length in piece_lengths:
        max_count = min(stock_length // (length + kerf_width), 20)  # Giới hạn 20 đoạn/loại
        max_counts.append(max_count)
    
    print(f"   Max counts per segment: {max_counts}")
    
    # Ước tính số tổ hợp
    total_combinations = 1
    for mc in max_counts:
        total_combinations *= (mc + 1)
    print(f"   Tổng tổ hợp ước tính: {total_combinations:,}")
    
    if total_combinations > 50_000_000:
        print(f"   ⚠️ Quá nhiều tổ hợp! Giảm max_counts...")
        # Giảm xuống 10 đoạn/loại
        max_counts = [min(mc, 10) for mc in max_counts]
        total_combinations = 1
        for mc in max_counts:
            total_combinations *= (mc + 1)
        print(f"   Tổng tổ hợp mới: {total_combinations:,}")
    
    patterns = []
    count = 0
    limit = 300000
    
    # Tạo ranges cho itertools.product
    ranges = [range(mc + 1) for mc in max_counts]
    
    for combo in product(*ranges):
        if sum(combo) == 0:
            continue
        
        # Tính tổng chiều dài sử dụng
        total_length = sum(combo[i] * piece_lengths[i] for i in range(n))
        total_kerf = sum(combo) * kerf_width
        total_used = total_length + total_kerf + trim_start
        
        if total_used <= stock_length and total_used >= min_used:
            waste = stock_length - total_used
            patterns.append(list(combo) + [waste])
            
            if len(patterns) >= limit:
                print(f"   ⚠️ Đạt giới hạn {limit:,} patterns")
                break
        
        count += 1
        if count % 5_000_000 == 0:
            print(f"   Đã duyệt {count:,} tổ hợp, tìm được {len(patterns):,} patterns...")
    
    # Sắp xếp theo hao hụt
    patterns.sort(key=lambda x: x[-1])
    
    print(f"   ✅ Tìm được {len(patterns):,} patterns")
    return patterns

# ===================================================================
# PHASE 2: PHÂN BỔ SỬ DỤNG CP-SAT
# ===================================================================
def solve_distribution(patterns, piece_lengths, demands, max_surplus, time_limit):
    print(f"\n🔧 PHASE 2: Phân bổ {len(patterns):,} patterns")
    
    model = cp_model.CpModel()
    num_patterns = len(patterns)
    num_pieces = len(piece_lengths)
    
    max_bars = sum(demands) * 2
    x = [model.NewIntVar(0, max_bars, f'x_{j}') for j in range(num_patterns)]
    
    surplus_vars = []
    for i in range(num_pieces):
        produced = sum(x[j] * patterns[j][i] for j in range(num_patterns))
        model.Add(produced >= demands[i])
        
        surplus = model.NewIntVar(0, max_bars * 10, f'surplus_{i}')
        model.Add(surplus == produced - demands[i])
        model.Add(surplus <= max_surplus)
        surplus_vars.append(surplus)
    
    # Minimize waste
    total_waste = sum(x[j] * patterns[j][-1] for j in range(num_patterns))
    model.Minimize(total_waste)
    
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    
    print(f"   Đang giải (timeout: {time_limit}s)...")
    status = solver.Solve(model)
    
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        print(f"   ✅ Thành công! Status: {solver.StatusName(status)}")
        
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
        print(f"   ❌ Thất bại! Status: {solver.StatusName(status)}")
        return None

# ===================================================================
# MAIN
# ===================================================================
if __name__ == "__main__":
    STOCK_LENGTH = 9000
    KERF_WIDTH = 1
    TRIM_START = 10
    MAX_WASTE_PCT = 0.20  # 20% để có đủ patterns
    MAX_SURPLUS = 500
    TIME_LIMIT = 300
    
    print("=" * 70)
    print("GIẢI BÀI TOÁN CẮT SẮT CO-2201-00249 - PHIÊN BẢN CUỐI")
    print("=" * 70)
    
    # Gộp dữ liệu
    merged_data = merge_by_length(RAW_DATA)
    piece_lengths = [m['length'] for m in merged_data]
    demands = [m['total_qty'] for m in merged_data]
    
    print(f"\n📊 DỮ LIỆU:")
    print(f"   Số chiều dài: {len(piece_lengths)}")
    print(f"   Tổng số lượng: {sum(demands):,}")
    print(f"   Chiều dài: {piece_lengths}")
    print(f"   Nhu cầu: {demands}")
    
    # Tạo patterns
    patterns = generate_patterns_bruteforce(
        STOCK_LENGTH, piece_lengths, KERF_WIDTH, TRIM_START, MAX_WASTE_PCT
    )
    
    if not patterns:
        print("\n❌ Không tạo được patterns!")
        sys.exit(1)
    
    # Kiểm tra coverage
    print("\n📋 Kiểm tra coverage:")
    all_covered = True
    for i, length in enumerate(piece_lengths):
        max_qty = max(p[i] for p in patterns)
        count = sum(1 for p in patterns if p[i] > 0)
        status = "✅" if count > 0 else "❌"
        if count == 0:
            all_covered = False
        print(f"   {status} {length}mm: max {max_qty}/pattern, có trong {count:,} patterns")
    
    if not all_covered:
        print("\n⚠️ Một số đoạn không được cover!")
        print("   Đang thử giảm ràng buộc...")
        
        # Thử với 30% waste
        MAX_WASTE_PCT = 0.30
        patterns = generate_patterns_bruteforce(
            STOCK_LENGTH, piece_lengths, KERF_WIDTH, TRIM_START, MAX_WASTE_PCT
        )
        
        print("\n📋 Kiểm tra lại coverage:")
        all_covered = True
        for i, length in enumerate(piece_lengths):
            max_qty = max(p[i] for p in patterns) if patterns else 0
            count = sum(1 for p in patterns if p[i] > 0) if patterns else 0
            status = "✅" if count > 0 else "❌"
            if count == 0:
                all_covered = False
            print(f"   {status} {length}mm: max {max_qty}/pattern, có trong {count:,} patterns")
    
    if not all_covered:
        print("\n❌ THẤT BẠI: Không thể tạo patterns cover tất cả đoạn!")
        print("   Vui lòng chia đơn hàng thành các lô nhỏ hơn.")
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
        print(f"   Tổng hao hụt: {result['total_waste'] / 1000:.2f}m ({waste_pct:.2f}%)")
        print(f"   Tổng tồn kho: {sum(result['surplus'])} đoạn")
        
        print(f"\n📊 CHI TIẾT:")
        print("-" * 60)
        for i, m in enumerate(merged_data):
            cat = result['production'][i]
            ton = result['surplus'][i]
            items = ", ".join([f"{it[0]}" for it in m['items']])
            print(f"   {m['length']:>4}mm: Cần {m['total_qty']:>4}, Cắt {cat:>4}, Tồn {ton:>3}")
        
        print(f"\n🔧 KẾ HOẠCH CẮT ({len(result['patterns_used'])} loại):")
        for idx, pu in enumerate(result['patterns_used'][:20], 1):  # Hiển thị 20 pattern đầu
            pattern = pu['pattern']
            count = pu['count']
            waste = pu['waste_mm']
            segs = ", ".join([f"{merged_data[i]['length']}×{pattern[i]}" for i in range(len(pattern)) if pattern[i] > 0])
            print(f"   P{idx:>2}: {segs:<50} | Hao hụt {waste:>4}mm | ×{count:>3}")
        
        if len(result['patterns_used']) > 20:
            print(f"   ... và {len(result['patterns_used']) - 20} loại pattern khác")
        
        # Lưu file
        output_file = os.path.join(os.path.dirname(__file__), "docs", "KET_QUA_CO-2201-00249.txt")
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("KẾT QUẢ TỐI ƯU CẮT SẮT CO-2201-00249\n")
            f.write("=" * 60 + "\n\n")
            f.write(f"Chiều dài cây sắt: {STOCK_LENGTH}mm\n")
            f.write(f"Tổng số cây sắt: {result['total_bars']} cây\n")
            f.write(f"Tổng hao hụt: {result['total_waste']/1000:.2f}m ({waste_pct:.2f}%)\n")
            f.write(f"Tổng tồn kho: {sum(result['surplus'])} đoạn\n\n")
            
            f.write("CHI TIẾT TỪNG CHIỀU DÀI:\n")
            for i, m in enumerate(merged_data):
                f.write(f"{m['length']}mm: Cần {m['total_qty']}, Cắt {result['production'][i]}, Tồn {result['surplus'][i]}\n")
            
            f.write("\nKẾ HOẠCH CẮT:\n")
            for idx, pu in enumerate(result['patterns_used'], 1):
                pattern = pu['pattern']
                segs = ", ".join([f"{merged_data[i]['length']}×{pattern[i]}" for i in range(len(pattern)) if pattern[i] > 0])
                f.write(f"Pattern {idx}: {segs} | Hao hụt {pu['waste_mm']}mm | ×{pu['count']} cây\n")
        
        print(f"\n💾 Đã lưu: {output_file}")
    else:
        print("\n❌ THẤT BẠI!")
