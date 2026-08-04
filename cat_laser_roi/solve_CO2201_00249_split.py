"""
GIẢI BÀI TOÁN CO-2201-00249 - CHIA THÀNH 2 LÔ I3 VÀ I5
Giải pháp thực tế: Chia nhỏ đơn hàng để giảm độ phức tạp
"""
import os
import sys
from itertools import product
from ortools.sat.python import cp_model

# ===================================================================
# DATA I3 (11 dòng - sản phẩm I3)
# ===================================================================
DATA_I3 = [
    ("PHOI-I3.1.1", "V15 (1 tán)", 425, 100),
    ("PHOI-I3.1.2", "V15 (2 tán)", 420, 300),
    ("PHOI-I3.1.4", "V15 (1 dập)", 445, 200),
    ("PHOI-I3.1.4", "V15 (2 dập)", 400, 200),
    ("PHOI-I3.1.4", "V15 (1 dập)", 175, 200),
    ("PHOI-I3.2.1", "V15 (2 dập)", 367, 50),
    ("PHOI-I3.2.1", "V15", 367, 50),
    ("PHOI-I3.2.2", "V15", 324, 200),
    ("PHOI-I3.2.2", "V15 (4 dập)", 330, 200),
    ("PHOI-I3.2.3", "V15 (2 tán)", 367, 200),
    ("PHOI-I3.2.3", "V15", 397, 200),
]

# ===================================================================
# DATA I5 (12 dòng - sản phẩm I5)
# ===================================================================
DATA_I5 = [
    ("PHOI-I5.1.1", "V15", 850, 100),
    ("PHOI-I5.1.2", "V15", 420, 600),
    ("PHOI-I5.1.4", "V15", 870, 200),
    ("PHOI-I5.1.4", "V15", 400, 700),
    ("PHOI-I5.1.4", "V15", 175, 600),
    ("PHOI-I5.2.1", "V15", 425, 200),
    ("PHOI-I5.2.4", "V15", 445, 400),
    ("PHOI-I5.3.1", "V15", 365, 200),
    ("PHOI-I5.3.1", "V15", 405, 100),
    ("PHOI-I5.3.1", "V15", 375, 100),
    ("PHOI-I5.3.2", "V15", 665, 200),
    ("PHOI-I5.3.2", "V15", 145, 400),
]

def merge_by_length(data):
    """Gộp các đoạn cùng chiều dài"""
    merged = {}
    for ma, ten, dai, sl in data:
        if dai not in merged:
            merged[dai] = {'length': dai, 'total_qty': 0, 'items': []}
        merged[dai]['total_qty'] += sl
        merged[dai]['items'].append((ma, ten, sl))
    return sorted(merged.values(), key=lambda x: -x['length'])

def generate_patterns(stock_length, piece_lengths, kerf_width, trim_start, max_waste_pct, limit=200000):
    """Tạo patterns bằng brute-force với giới hạn hợp lý"""
    n = len(piece_lengths)
    min_used = int(stock_length * (1 - max_waste_pct))
    
    # Tính max cho từng loại
    max_counts = []
    for length in piece_lengths:
        max_count = min(stock_length // (length + kerf_width), 25)
        max_counts.append(max_count)
    
    patterns = []
    ranges = [range(mc + 1) for mc in max_counts]
    
    for combo in product(*ranges):
        if sum(combo) == 0:
            continue
        
        total_length = sum(combo[i] * piece_lengths[i] for i in range(n))
        total_kerf = sum(combo) * kerf_width
        total_used = total_length + total_kerf + trim_start
        
        if total_used <= stock_length and total_used >= min_used:
            waste = stock_length - total_used
            patterns.append(list(combo) + [waste])
            
            if len(patterns) >= limit:
                break
    
    patterns.sort(key=lambda x: x[-1])
    return patterns

def solve_phase2(patterns, piece_lengths, demands, max_surplus, time_limit):
    """Giải Phase 2"""
    if not patterns:
        return None
    
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
    
    total_waste = sum(x[j] * patterns[j][-1] for j in range(num_patterns))
    model.Minimize(total_waste)
    
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    
    status = solver.Solve(model)
    
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
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
    return None

def solve_suborder(name, data, stock_length, kerf_width=1, trim_start=10, 
                   max_waste_pct=0.15, max_surplus=200, time_limit=120):
    """Giải một sub-order"""
    print(f"\n{'='*60}")
    print(f"GIẢI SUB-ORDER: {name}")
    print(f"{'='*60}")
    
    # Gộp dữ liệu
    merged = merge_by_length(data)
    piece_lengths = [m['length'] for m in merged]
    demands = [m['total_qty'] for m in merged]
    
    print(f"   Số chiều dài: {len(piece_lengths)}")
    print(f"   Tổng số lượng: {sum(demands):,}")
    print(f"   Stock length: {stock_length}mm")
    print(f"   Max waste: {max_waste_pct*100:.0f}%")
    
    for m in merged:
        items = ", ".join([f"{it[0]}×{it[2]}" for it in m['items']])
        print(f"   - {m['length']}mm: {m['total_qty']} ({items})")
    
    # Phase 1
    print(f"\n🔍 Tìm patterns...")
    patterns = generate_patterns(stock_length, piece_lengths, kerf_width, trim_start, max_waste_pct)
    print(f"   ✅ Tìm được {len(patterns):,} patterns")
    
    # Kiểm tra coverage
    all_covered = True
    for i, length in enumerate(piece_lengths):
        has_pattern = any(p[i] > 0 for p in patterns)
        if not has_pattern:
            all_covered = False
            print(f"   ❌ {length}mm: KHÔNG có pattern!")
    
    if not all_covered:
        print(f"   ⚠️ Thử tăng max_waste lên 25%...")
        patterns = generate_patterns(stock_length, piece_lengths, kerf_width, trim_start, 0.25)
        print(f"   Tìm được {len(patterns):,} patterns")
    
    # Phase 2
    print(f"\n🔧 Phân bổ patterns...")
    result = solve_phase2(patterns, piece_lengths, demands, max_surplus, time_limit)
    
    if result:
        waste_pct = (result['total_waste'] / (result['total_bars'] * stock_length)) * 100
        print(f"\n✅ {name} THÀNH CÔNG!")
        print(f"   Số cây sắt: {result['total_bars']}")
        print(f"   Hao hụt: {result['total_waste']/1000:.2f}m ({waste_pct:.2f}%)")
        print(f"   Tồn kho: {sum(result['surplus'])} đoạn")
        
        return {
            'name': name,
            'stock_length': stock_length,
            'merged_data': merged,
            'result': result
        }
    else:
        print(f"\n❌ {name} THẤT BẠI!")
        return None

# ===================================================================
# MAIN
# ===================================================================
if __name__ == "__main__":
    print("=" * 70)
    print("GIẢI BÀI TOÁN CO-2201-00249 - CHIA 2 LÔ I3 VÀ I5")
    print("=" * 70)
    
    results = []
    
    # Giải I3 với stock_length = 6000mm (đoạn max = 445mm)
    r1 = solve_suborder(
        name="CO-2201-00249-I3",
        data=DATA_I3,
        stock_length=6000,
        max_waste_pct=0.15,
        max_surplus=150,
        time_limit=120
    )
    if r1:
        results.append(r1)
    
    # Giải I5 với stock_length = 9000mm (có đoạn 870mm)
    r2 = solve_suborder(
        name="CO-2201-00249-I5",
        data=DATA_I5,
        stock_length=9000,
        max_waste_pct=0.15,
        max_surplus=200,
        time_limit=180
    )
    if r2:
        results.append(r2)
    
    # Tổng kết
    print("\n" + "=" * 70)
    print("TỔNG KẾT")
    print("=" * 70)
    
    if len(results) == 2:
        total_bars = sum(r['result']['total_bars'] for r in results)
        total_waste = sum(r['result']['total_waste'] for r in results)
        total_surplus = sum(sum(r['result']['surplus']) for r in results)
        
        # Tính tổng chiều dài sử dụng
        total_length_used = sum(r['result']['total_bars'] * r['stock_length'] for r in results)
        waste_pct = (total_waste / total_length_used) * 100
        
        print(f"\n📦 KẾT QUẢ TỔNG HỢP 2 LÔ:")
        print(f"   Tổng số cây sắt: {total_bars} cây")
        print(f"   - I3 (6000mm): {results[0]['result']['total_bars']} cây")
        print(f"   - I5 (9000mm): {results[1]['result']['total_bars']} cây")
        print(f"   Tổng hao hụt: {total_waste/1000:.2f}m ({waste_pct:.2f}%)")
        print(f"   Tổng tồn kho: {total_surplus} đoạn")
        
        # Lưu kết quả
        output_file = os.path.join(os.path.dirname(__file__), "docs", "KET_QUA_CO-2201-00249.txt")
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("=" * 60 + "\n")
            f.write("KẾT QUẢ TỐI ƯU CẮT SẮT CO-2201-00249\n")
            f.write("CHIA THÀNH 2 LÔ: I3 VÀ I5\n")
            f.write("=" * 60 + "\n\n")
            
            f.write(f"TỔNG KẾT:\n")
            f.write(f"  Tổng số cây sắt: {total_bars} cây\n")
            f.write(f"  Tổng hao hụt: {total_waste/1000:.2f}m ({waste_pct:.2f}%)\n")
            f.write(f"  Tổng tồn kho: {total_surplus} đoạn\n\n")
            
            for r in results:
                f.write(f"\n{'='*60}\n")
                f.write(f"{r['name']} (Stock: {r['stock_length']}mm)\n")
                f.write(f"{'='*60}\n")
                f.write(f"Số cây: {r['result']['total_bars']}\n")
                f.write(f"Hao hụt: {r['result']['total_waste']/1000:.2f}m\n")
                f.write(f"Tồn kho: {sum(r['result']['surplus'])} đoạn\n\n")
                
                f.write("Chi tiết:\n")
                for i, m in enumerate(r['merged_data']):
                    f.write(f"  {m['length']}mm: Cần {m['total_qty']}, Cắt {r['result']['production'][i]}, Tồn {r['result']['surplus'][i]}\n")
                
                f.write("\nKế hoạch cắt:\n")
                for idx, pu in enumerate(r['result']['patterns_used'], 1):
                    pattern = pu['pattern']
                    segs = ", ".join([f"{r['merged_data'][i]['length']}×{pattern[i]}" for i in range(len(pattern)) if pattern[i] > 0])
                    f.write(f"  P{idx}: {segs} | Hao hụt {pu['waste_mm']}mm | ×{pu['count']} cây\n")
        
        print(f"\n💾 Đã lưu kết quả: {output_file}")
        
        # In kế hoạch cắt chi tiết
        for r in results:
            print(f"\n📋 KẾ HOẠCH CẮT {r['name']} (Stock {r['stock_length']}mm):")
            print("-" * 60)
            for idx, pu in enumerate(r['result']['patterns_used'], 1):
                pattern = pu['pattern']
                segs = ", ".join([f"{r['merged_data'][i]['length']}×{pattern[i]}" for i in range(len(pattern)) if pattern[i] > 0])
                print(f"  P{idx:>2}: {segs:<45} | Hao hụt {pu['waste_mm']:>4}mm | ×{pu['count']:>3} cây")
    else:
        print("\n❌ Một hoặc cả hai lô đều thất bại!")
        print("   Vui lòng kiểm tra lại dữ liệu hoặc tăng max_waste/max_surplus")
