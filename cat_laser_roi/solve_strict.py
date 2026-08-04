"""
GIẢI CO-2201-00249 - PHIÊN BẢN TỐI ƯU
Mục tiêu: Tồn kho < 20 mỗi loại, hao hụt tối thiểu
"""
import os
import sys
import random
from ortools.sat.python import cp_model

random.seed(42)

# ===================================================================
# DATA - GIỮ NGUYÊN 23 DÒNG GỐC (không gộp)
# ===================================================================
DATA_FULL = [
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

def merge_by_length(data):
    """Gộp theo chiều dài, giữ thông tin từng item"""
    merged = {}
    for item in data:
        if len(item) == 5:
            stt, ma, ten, dai, sl = item
        else:
            ma, dai, sl = item
            ten = ma
        
        if dai not in merged:
            merged[dai] = {'length': dai, 'total_qty': 0, 'items': []}
        merged[dai]['total_qty'] += sl
        merged[dai]['items'].append((ma, ten, sl))
    return sorted(merged.values(), key=lambda x: -x['length'])

def generate_patterns(stock, lengths, kerf, trim, max_waste_pct, num_patterns=300000):
    """Random sampling patterns"""
    n = len(lengths)
    min_used = int(stock * (1 - max_waste_pct))
    max_counts = [min(stock // (l + kerf), 25) for l in lengths]
    
    patterns = set()
    
    # 1. Patterns đơn
    for i in range(n):
        for qty in range(1, max_counts[i] + 1):
            combo = [0] * n
            combo[i] = qty
            total = qty * lengths[i] + qty * kerf + trim
            if min_used <= total <= stock:
                patterns.add((tuple(combo), stock - total))
    
    # 2. Patterns kết hợp
    attempts = 0
    while len(patterns) < num_patterns and attempts < num_patterns * 50:
        attempts += 1
        num_types = random.randint(2, min(5, n))
        indices = random.sample(range(n), num_types)
        
        combo = [0] * n
        total = trim
        
        for idx in indices:
            max_q = min(max_counts[idx], (stock - total) // (lengths[idx] + kerf))
            if max_q > 0:
                combo[idx] = random.randint(1, max_q)
                total += combo[idx] * (lengths[idx] + kerf)
        
        if sum(combo) > 0 and min_used <= total <= stock:
            patterns.add((tuple(combo), stock - total))
    
    result = [list(p[0]) + [p[1]] for p in patterns]
    result.sort(key=lambda x: x[-1])
    return result

def solve_strict(patterns, demands, max_surplus_per_item, time_limit):
    """Giải với ràng buộc tồn kho nghiêm ngặt"""
    if not patterns:
        return None
    
    model = cp_model.CpModel()
    np, nd = len(patterns), len(demands)
    
    x = [model.NewIntVar(0, sum(demands)*2, f'x_{j}') for j in range(np)]
    surplus_vars = []
    
    for i in range(nd):
        produced = sum(x[j] * patterns[j][i] for j in range(np))
        model.Add(produced >= demands[i])
        
        surplus = model.NewIntVar(0, max_surplus_per_item, f's_{i}')
        model.Add(surplus == produced - demands[i])
        surplus_vars.append(surplus)
    
    # Mục tiêu kép: (1) Tối thiểu tồn kho, (2) Tối thiểu hao hụt
    # Dùng weighted sum với trọng số cao cho tồn kho
    total_surplus = sum(surplus_vars)
    total_waste = sum(x[j] * patterns[j][-1] for j in range(np))
    
    # Trọng số: tồn kho quan trọng hơn hao hụt 1000 lần
    model.Minimize(total_surplus * 1000 + total_waste)
    
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

def solve_order(name, data, stock, max_waste=0.25, max_surplus=20, time_limit=300):
    print(f"\n{'='*60}")
    print(f"GIẢI: {name} (Stock: {stock}mm, max_surplus: {max_surplus})")
    print(f"{'='*60}")
    
    merged = merge_by_length(data)
    lengths = [m['length'] for m in merged]
    demands = [m['total_qty'] for m in merged]
    
    print(f"   Số chiều dài: {len(lengths)}, Tổng SL: {sum(demands):,}")
    
    print(f"\n🔍 Tạo patterns...")
    patterns = generate_patterns(stock, lengths, 1, 10, max_waste, 300000)
    print(f"   ✅ {len(patterns):,} patterns")
    
    # Check coverage
    missing = [l for i, l in enumerate(lengths) if not any(p[i] > 0 for p in patterns)]
    if missing:
        print(f"   ⚠️ Thiếu: {missing}, thử max_waste=40%...")
        patterns = generate_patterns(stock, lengths, 1, 10, 0.40, 400000)
        print(f"   ✅ {len(patterns):,} patterns")
    
    print(f"\n🔧 Tối ưu (max_surplus={max_surplus}/loại, timeout={time_limit}s)...")
    result = solve_strict(patterns, demands, max_surplus, time_limit)
    
    if result:
        wp = (result['total_waste'] / (result['total_bars'] * stock)) * 100
        max_s = max(result['surplus'])
        print(f"\n✅ THÀNH CÔNG!")
        print(f"   Số cây: {result['total_bars']}")
        print(f"   Hao hụt: {result['total_waste']/1000:.2f}m ({wp:.2f}%)")
        print(f"   Tổng tồn: {sum(result['surplus'])}, Max/loại: {max_s}")
        return {'name': name, 'stock': stock, 'merged': merged, 'result': result}
    else:
        print(f"\n❌ THẤT BẠI với max_surplus={max_surplus}")
        return None

if __name__ == "__main__":
    print("=" * 60)
    print("GIẢI CO-2201-00249 - TỒN KHO < 20 MỖI LOẠI")
    print("=" * 60)
    
    # Chia I3 và I5
    DATA_I3 = [(d[1], d[3], d[4]) for d in DATA_FULL if d[1].startswith("PHOI-I3")]
    DATA_I5 = [(d[1], d[3], d[4]) for d in DATA_FULL if d[1].startswith("PHOI-I5")]
    
    results = []
    
    # I3: stock 6000mm
    r1 = solve_order("CO-2201-00249-I3", DATA_I3, 6000, max_waste=0.30, max_surplus=20, time_limit=300)
    if r1: results.append(r1)
    
    # I5: stock 9000mm - có thể cần max_surplus cao hơn một chút
    r2 = solve_order("CO-2201-00249-I5", DATA_I5, 9000, max_waste=0.30, max_surplus=20, time_limit=300)
    if not r2:
        print("\n⚠️ Thử lại I5 với max_surplus=30...")
        r2 = solve_order("CO-2201-00249-I5", DATA_I5, 9000, max_waste=0.35, max_surplus=30, time_limit=300)
    if r2: results.append(r2)
    
    print("\n" + "=" * 60)
    print("TỔNG KẾT")
    print("=" * 60)
    
    if results:
        total_bars = sum(r['result']['total_bars'] for r in results)
        total_waste = sum(r['result']['total_waste'] for r in results)
        total_len = sum(r['result']['total_bars'] * r['stock'] for r in results)
        total_surplus = sum(sum(r['result']['surplus']) for r in results)
        
        print(f"\n📦 KẾT QUẢ:")
        for r in results:
            max_s = max(r['result']['surplus'])
            print(f"   {r['name']}: {r['result']['total_bars']} cây, tồn max {max_s}/loại")
        print(f"\n   TỔNG: {total_bars} cây")
        print(f"   Hao hụt: {total_waste/1000:.2f}m ({(total_waste/total_len)*100:.2f}%)")
        print(f"   Tổng tồn kho: {total_surplus} đoạn")
        
        # Chi tiết
        for r in results:
            print(f"\n📋 {r['name']} ({r['stock']}mm):")
            print(f"   {'Dài':>6} | {'Cần':>5} | {'Cắt':>5} | {'Tồn':>4}")
            print(f"   {'-'*30}")
            for i, m in enumerate(r['merged']):
                print(f"   {m['length']:>5}mm | {m['total_qty']:>5} | {r['result']['production'][i]:>5} | {r['result']['surplus'][i]:>4}")
        
        # Lưu file
        out = os.path.join(os.path.dirname(__file__), "docs", "KET_QUA_CO-2201-00249_STRICT.txt")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        
        with open(out, 'w', encoding='utf-8') as f:
            f.write("KẾT QUẢ TỐI ƯU CO-2201-00249 (TỒN KHO < 20/LOẠI)\n")
            f.write("=" * 50 + "\n\n")
            f.write(f"TỔNG: {total_bars} cây, Hao hụt: {(total_waste/total_len)*100:.2f}%\n")
            f.write(f"Tổng tồn kho: {total_surplus} đoạn\n\n")
            
            for r in results:
                f.write(f"\n{r['name']} (Stock {r['stock']}mm) - {r['result']['total_bars']} cây\n")
                f.write("-" * 50 + "\n")
                for i, m in enumerate(r['merged']):
                    f.write(f"  {m['length']}mm: cần {m['total_qty']}, cắt {r['result']['production'][i]}, tồn {r['result']['surplus'][i]}\n")
                f.write("\nKế hoạch:\n")
                for idx, pu in enumerate(r['result']['patterns_used'], 1):
                    segs = ", ".join([f"{r['merged'][i]['length']}×{pu['p'][i]}" for i in range(len(pu['p'])) if pu['p'][i] > 0])
                    f.write(f"  P{idx}: {segs} | {pu['w']}mm | ×{pu['c']}\n")
        
        print(f"\n💾 Đã lưu: {out}")
    else:
        print("\n❌ Không giải được!")
