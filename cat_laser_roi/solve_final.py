"""
GIẢI BÀI TOÁN CO-2201-00249 - PHIÊN BẢN CUỐI CÙNG
Đảm bảo coverage bằng cách ĐẢO NGƯỢC thứ tự (duyệt đoạn dài trước)
"""
import os
import sys
from itertools import product
from ortools.sat.python import cp_model

# ===================================================================
# DATA I3
# ===================================================================
DATA_I3 = [
    ("PHOI-I3.1.1", 425, 100),
    ("PHOI-I3.1.2", 420, 300),
    ("PHOI-I3.1.4a", 445, 200),
    ("PHOI-I3.1.4b", 400, 200),
    ("PHOI-I3.1.4c", 175, 200),
    ("PHOI-I3.2.1a", 367, 50),
    ("PHOI-I3.2.1b", 367, 50),
    ("PHOI-I3.2.2a", 324, 200),
    ("PHOI-I3.2.2b", 330, 200),
    ("PHOI-I3.2.3a", 367, 200),
    ("PHOI-I3.2.3b", 397, 200),
]

# ===================================================================
# DATA I5
# ===================================================================
DATA_I5 = [
    ("PHOI-I5.1.1", 850, 100),
    ("PHOI-I5.1.2", 420, 600),
    ("PHOI-I5.1.4a", 870, 200),
    ("PHOI-I5.1.4b", 400, 700),
    ("PHOI-I5.1.4c", 175, 600),
    ("PHOI-I5.2.1", 425, 200),
    ("PHOI-I5.2.4", 445, 400),
    ("PHOI-I5.3.1a", 365, 200),
    ("PHOI-I5.3.1b", 405, 100),
    ("PHOI-I5.3.1c", 375, 100),
    ("PHOI-I5.3.2a", 665, 200),
    ("PHOI-I5.3.2b", 145, 400),
]

def merge_by_length(data):
    merged = {}
    for ma, dai, sl in data:
        if dai not in merged:
            merged[dai] = {'length': dai, 'total_qty': 0, 'items': []}
        merged[dai]['total_qty'] += sl
        merged[dai]['items'].append((ma, sl))
    # SẮP XẾP THEO THỨ TỰ TĂNG DẦN (đoạn ngắn trước) để product duyệt đoạn dài trước
    return sorted(merged.values(), key=lambda x: x['length'])

def generate_patterns_reversed(stock_length, piece_lengths, kerf, trim, max_waste_pct, limit=300000):
    """Tạo patterns với thứ tự đảo ngược để cover đoạn dài trước"""
    n = len(piece_lengths)
    min_used = int(stock_length * (1 - max_waste_pct))
    
    max_counts = [min(stock_length // (l + kerf), 20) for l in piece_lengths]
    
    patterns = []
    # Đảo ngược ranges để duyệt từ giá trị lớn xuống nhỏ
    ranges = [range(mc, -1, -1) for mc in max_counts]
    
    count = 0
    for combo in product(*ranges):
        if sum(combo) == 0:
            continue
        
        total = sum(combo[i] * piece_lengths[i] for i in range(n))
        total += sum(combo) * kerf + trim
        
        if min_used <= total <= stock_length:
            waste = stock_length - total
            patterns.append(list(combo) + [waste])
            
            if len(patterns) >= limit:
                break
        
        count += 1
        if count % 10_000_000 == 0:
            print(f"   Duyệt {count:,}, patterns: {len(patterns):,}")
    
    patterns.sort(key=lambda x: x[-1])
    return patterns

def solve_phase2(patterns, demands, max_surplus, time_limit):
    if not patterns:
        return None
    
    model = cp_model.CpModel()
    np = len(patterns)
    nd = len(demands)
    
    x = [model.NewIntVar(0, sum(demands)*2, f'x_{j}') for j in range(np)]
    
    for i in range(nd):
        produced = sum(x[j] * patterns[j][i] for j in range(np))
        model.Add(produced >= demands[i])
        
        surplus = model.NewIntVar(0, sum(demands)*10, f's_{i}')
        model.Add(surplus == produced - demands[i])
        model.Add(surplus <= max_surplus)
    
    model.Minimize(sum(x[j] * patterns[j][-1] for j in range(np)))
    
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    
    status = solver.Solve(model)
    
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        result = {'patterns_used': [], 'total_bars': 0, 'total_waste': 0, 
                  'production': [0]*nd, 'surplus': [0]*nd}
        
        for j in range(np):
            c = solver.Value(x[j])
            if c > 0:
                result['patterns_used'].append({'p': patterns[j][:-1], 'c': c, 'w': patterns[j][-1]})
                result['total_bars'] += c
                result['total_waste'] += c * patterns[j][-1]
                for i in range(nd):
                    result['production'][i] += c * patterns[j][i]
        
        for i in range(nd):
            result['surplus'][i] = result['production'][i] - demands[i]
        
        return result
    return None

def solve_order(name, data, stock, max_waste=0.20, max_surplus=300, time_limit=180):
    print(f"\n{'='*60}")
    print(f"GIẢI: {name} (Stock: {stock}mm)")
    print(f"{'='*60}")
    
    merged = merge_by_length(data)
    lengths = [m['length'] for m in merged]
    demands = [m['total_qty'] for m in merged]
    
    print(f"   Số chiều dài: {len(lengths)}, Tổng SL: {sum(demands):,}")
    for m in merged:
        print(f"   - {m['length']}mm × {m['total_qty']}")
    
    print(f"\n🔍 Tìm patterns (max_waste={max_waste*100:.0f}%)...")
    patterns = generate_patterns_reversed(stock, lengths, 1, 10, max_waste)
    print(f"   ✅ {len(patterns):,} patterns")
    
    # Check coverage
    missing = []
    for i, l in enumerate(lengths):
        if not any(p[i] > 0 for p in patterns):
            missing.append(l)
            print(f"   ❌ {l}mm: không có pattern!")
    
    if missing:
        print(f"   ⚠️ Thiếu {len(missing)} loại, thử max_waste=35%...")
        patterns = generate_patterns_reversed(stock, lengths, 1, 10, 0.35, 500000)
        print(f"   Tìm được {len(patterns):,} patterns")
        
        missing = [l for i, l in enumerate(lengths) if not any(p[i] > 0 for p in patterns)]
        if missing:
            print(f"   ❌ Vẫn thiếu: {missing}")
            return None
    
    print(f"\n🔧 Phân bổ (max_surplus={max_surplus}, timeout={time_limit}s)...")
    result = solve_phase2(patterns, demands, max_surplus, time_limit)
    
    if result:
        wp = (result['total_waste'] / (result['total_bars'] * stock)) * 100
        print(f"\n✅ THÀNH CÔNG!")
        print(f"   Số cây: {result['total_bars']}, Hao hụt: {wp:.2f}%, Tồn kho: {sum(result['surplus'])}")
        return {'name': name, 'stock': stock, 'merged': merged, 'result': result}
    else:
        print(f"\n❌ THẤT BẠI!")
        return None

if __name__ == "__main__":
    print("=" * 60)
    print("GIẢI CO-2201-00249 - FINAL VERSION")
    print("=" * 60)
    
    results = []
    
    # I3: stock 6000mm (max đoạn 445mm)
    r1 = solve_order("CO-2201-00249-I3", DATA_I3, 6000, max_waste=0.20, max_surplus=200)
    if r1: results.append(r1)
    
    # I5: stock 9000mm (có đoạn 870mm)
    r2 = solve_order("CO-2201-00249-I5", DATA_I5, 9000, max_waste=0.20, max_surplus=300)
    if r2: results.append(r2)
    
    print("\n" + "=" * 60)
    print("TỔNG KẾT")
    print("=" * 60)
    
    if len(results) == 2:
        total_bars = sum(r['result']['total_bars'] for r in results)
        total_waste = sum(r['result']['total_waste'] for r in results)
        total_len = sum(r['result']['total_bars'] * r['stock'] for r in results)
        
        print(f"\n📦 KẾT QUẢ TỔNG HỢP:")
        print(f"   I3: {results[0]['result']['total_bars']} cây × 6000mm")
        print(f"   I5: {results[1]['result']['total_bars']} cây × 9000mm")
        print(f"   TỔNG: {total_bars} cây")
        print(f"   Hao hụt: {total_waste/1000:.2f}m ({(total_waste/total_len)*100:.2f}%)")
        print(f"   Tồn kho: {sum(sum(r['result']['surplus']) for r in results)} đoạn")
        
        # Lưu file
        out = os.path.join(os.path.dirname(__file__), "docs", "KET_QUA_CO-2201-00249.txt")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        
        with open(out, 'w', encoding='utf-8') as f:
            f.write("KẾT QUẢ TỐI ƯU CẮT SẮT CO-2201-00249\n")
            f.write("=" * 50 + "\n\n")
            f.write(f"TỔNG: {total_bars} cây sắt\n")
            f.write(f"Hao hụt: {total_waste/1000:.2f}m ({(total_waste/total_len)*100:.2f}%)\n\n")
            
            for r in results:
                f.write(f"\n{r['name']} (Stock {r['stock']}mm)\n")
                f.write(f"Số cây: {r['result']['total_bars']}\n")
                f.write(f"Hao hụt: {r['result']['total_waste']/1000:.2f}m\n")
                f.write(f"\nKế hoạch:\n")
                for idx, pu in enumerate(r['result']['patterns_used'], 1):
                    segs = ", ".join([f"{r['merged'][i]['length']}×{pu['p'][i]}" for i in range(len(pu['p'])) if pu['p'][i] > 0])
                    f.write(f"  P{idx}: {segs} | Hao hụt {pu['w']}mm | ×{pu['c']} cây\n")
        
        print(f"\n💾 Đã lưu: {out}")
        
        # In kế hoạch
        for r in results:
            print(f"\n📋 {r['name']}:")
            for idx, pu in enumerate(r['result']['patterns_used'][:15], 1):
                segs = ", ".join([f"{r['merged'][i]['length']}×{pu['p'][i]}" for i in range(len(pu['p'])) if pu['p'][i] > 0])
                print(f"   P{idx}: {segs} | {pu['w']}mm | ×{pu['c']}")
            if len(r['result']['patterns_used']) > 15:
                print(f"   ... +{len(r['result']['patterns_used'])-15} patterns khác")
    
    elif len(results) == 1:
        print(f"\n⚠️ Chỉ giải được 1 lô: {results[0]['name']}")
    else:
        print("\n❌ Cả 2 lô đều thất bại!")
