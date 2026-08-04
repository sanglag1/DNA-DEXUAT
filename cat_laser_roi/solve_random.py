"""
GIẢI CO-2201-00249 - RANDOM SAMPLING APPROACH
Đảm bảo coverage bằng cách sampling ngẫu nhiên các tổ hợp
"""
import os
import sys
import random
from ortools.sat.python import cp_model

random.seed(42)

# ===================================================================
# DATA
# ===================================================================
DATA_I3 = [
    ("PHOI-I3.1.1", 425, 100), ("PHOI-I3.1.2", 420, 300), ("PHOI-I3.1.4a", 445, 200),
    ("PHOI-I3.1.4b", 400, 200), ("PHOI-I3.1.4c", 175, 200), ("PHOI-I3.2.1a", 367, 50),
    ("PHOI-I3.2.1b", 367, 50), ("PHOI-I3.2.2a", 324, 200), ("PHOI-I3.2.2b", 330, 200),
    ("PHOI-I3.2.3a", 367, 200), ("PHOI-I3.2.3b", 397, 200),
]

DATA_I5 = [
    ("PHOI-I5.1.1", 850, 100), ("PHOI-I5.1.2", 420, 600), ("PHOI-I5.1.4a", 870, 200),
    ("PHOI-I5.1.4b", 400, 700), ("PHOI-I5.1.4c", 175, 600), ("PHOI-I5.2.1", 425, 200),
    ("PHOI-I5.2.4", 445, 400), ("PHOI-I5.3.1a", 365, 200), ("PHOI-I5.3.1b", 405, 100),
    ("PHOI-I5.3.1c", 375, 100), ("PHOI-I5.3.2a", 665, 200), ("PHOI-I5.3.2b", 145, 400),
]

def merge_by_length(data):
    merged = {}
    for ma, dai, sl in data:
        if dai not in merged:
            merged[dai] = {'length': dai, 'total_qty': 0, 'items': []}
        merged[dai]['total_qty'] += sl
        merged[dai]['items'].append((ma, sl))
    return sorted(merged.values(), key=lambda x: -x['length'])

def generate_random_patterns(stock, lengths, kerf, trim, max_waste_pct, num_patterns=300000):
    """Tạo patterns bằng random sampling - đảm bảo đa dạng"""
    n = len(lengths)
    min_used = int(stock * (1 - max_waste_pct))
    max_counts = [min(stock // (l + kerf), 25) for l in lengths]
    
    patterns = set()
    attempts = 0
    max_attempts = num_patterns * 100
    
    # Đầu tiên: tạo patterns đơn (chỉ 1 loại đoạn) để đảm bảo coverage
    print("   Tạo patterns đơn...")
    for i in range(n):
        for qty in range(1, max_counts[i] + 1):
            combo = [0] * n
            combo[i] = qty
            total = qty * lengths[i] + qty * kerf + trim
            if min_used <= total <= stock:
                waste = stock - total
                patterns.add((tuple(combo), waste))
    
    print(f"   Tạo được {len(patterns)} patterns đơn")
    
    # Sau đó: tạo patterns kết hợp ngẫu nhiên
    print("   Tạo patterns kết hợp...")
    while len(patterns) < num_patterns and attempts < max_attempts:
        attempts += 1
        
        # Random số loại đoạn trong pattern (2-5 loại)
        num_types = random.randint(2, min(5, n))
        selected_indices = random.sample(range(n), num_types)
        
        combo = [0] * n
        total = trim
        
        for idx in selected_indices:
            max_qty = min(max_counts[idx], (stock - total) // (lengths[idx] + kerf))
            if max_qty > 0:
                qty = random.randint(1, max_qty)
                combo[idx] = qty
                total += qty * (lengths[idx] + kerf)
        
        if sum(combo) > 0 and min_used <= total <= stock:
            waste = stock - total
            patterns.add((tuple(combo), waste))
        
        if attempts % 1000000 == 0:
            print(f"   Attempts: {attempts:,}, patterns: {len(patterns):,}")
    
    # Chuyển thành list và sắp xếp
    result = [list(p[0]) + [p[1]] for p in patterns]
    result.sort(key=lambda x: x[-1])
    
    return result

def solve_phase2(patterns, demands, max_surplus, time_limit):
    if not patterns:
        return None
    
    model = cp_model.CpModel()
    np, nd = len(patterns), len(demands)
    
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

def solve_order(name, data, stock, max_waste=0.25, max_surplus=300, time_limit=180):
    print(f"\n{'='*60}")
    print(f"GIẢI: {name} (Stock: {stock}mm)")
    print(f"{'='*60}")
    
    merged = merge_by_length(data)
    lengths = [m['length'] for m in merged]
    demands = [m['total_qty'] for m in merged]
    
    print(f"   Số chiều dài: {len(lengths)}, Tổng SL: {sum(demands):,}")
    for m in merged:
        print(f"   - {m['length']}mm × {m['total_qty']}")
    
    print(f"\n🔍 Tạo patterns (random sampling, max_waste={max_waste*100:.0f}%)...")
    patterns = generate_random_patterns(stock, lengths, 1, 10, max_waste, 200000)
    print(f"   ✅ {len(patterns):,} patterns")
    
    # Check coverage
    print("   Kiểm tra coverage:")
    all_ok = True
    for i, l in enumerate(lengths):
        count = sum(1 for p in patterns if p[i] > 0)
        max_q = max(p[i] for p in patterns) if count > 0 else 0
        status = "✅" if count > 0 else "❌"
        print(f"   {status} {l}mm: {count:,} patterns (max {max_q}/pattern)")
        if count == 0:
            all_ok = False
    
    if not all_ok:
        print("   ❌ Thiếu coverage!")
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
    print("GIẢI CO-2201-00249 - RANDOM SAMPLING")
    print("=" * 60)
    
    results = []
    
    r1 = solve_order("CO-2201-00249-I3", DATA_I3, 6000, max_waste=0.25, max_surplus=250)
    if r1: results.append(r1)
    
    r2 = solve_order("CO-2201-00249-I5", DATA_I5, 9000, max_waste=0.25, max_surplus=350)
    if r2: results.append(r2)
    
    print("\n" + "=" * 60)
    print("TỔNG KẾT")
    print("=" * 60)
    
    if len(results) == 2:
        total_bars = sum(r['result']['total_bars'] for r in results)
        total_waste = sum(r['result']['total_waste'] for r in results)
        total_len = sum(r['result']['total_bars'] * r['stock'] for r in results)
        
        print(f"\n📦 KẾT QUẢ:")
        print(f"   I3: {results[0]['result']['total_bars']} cây × 6000mm")
        print(f"   I5: {results[1]['result']['total_bars']} cây × 9000mm")
        print(f"   TỔNG: {total_bars} cây")
        print(f"   Hao hụt: {total_waste/1000:.2f}m ({(total_waste/total_len)*100:.2f}%)")
        
        # Lưu
        out = os.path.join(os.path.dirname(__file__), "docs", "KET_QUA_CO-2201-00249.txt")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        
        with open(out, 'w', encoding='utf-8') as f:
            f.write("KẾT QUẢ TỐI ƯU CẮT SẮT CO-2201-00249\n")
            f.write("=" * 50 + "\n\n")
            f.write(f"TỔNG: {total_bars} cây sắt\n")
            f.write(f"Hao hụt: {total_waste/1000:.2f}m ({(total_waste/total_len)*100:.2f}%)\n\n")
            
            for r in results:
                f.write(f"\n{r['name']} (Stock {r['stock']}mm) - {r['result']['total_bars']} cây\n")
                f.write("-" * 50 + "\n")
                for i, m in enumerate(r['merged']):
                    f.write(f"  {m['length']}mm: cần {m['total_qty']}, cắt {r['result']['production'][i]}, tồn {r['result']['surplus'][i]}\n")
                f.write("\nKế hoạch cắt:\n")
                for idx, pu in enumerate(r['result']['patterns_used'], 1):
                    segs = ", ".join([f"{r['merged'][i]['length']}×{pu['p'][i]}" for i in range(len(pu['p'])) if pu['p'][i] > 0])
                    f.write(f"  P{idx}: {segs} | hao hụt {pu['w']}mm | ×{pu['c']} cây\n")
        
        print(f"\n💾 Đã lưu: {out}")
        
        for r in results:
            print(f"\n📋 {r['name']}:")
            for idx, pu in enumerate(r['result']['patterns_used'][:10], 1):
                segs = ", ".join([f"{r['merged'][i]['length']}×{pu['p'][i]}" for i in range(len(pu['p'])) if pu['p'][i] > 0])
                print(f"   P{idx}: {segs} | {pu['w']}mm | ×{pu['c']}")
            if len(r['result']['patterns_used']) > 10:
                print(f"   ... +{len(r['result']['patterns_used'])-10} patterns")
    else:
        print(f"\n⚠️ Chỉ giải được {len(results)} lô")
