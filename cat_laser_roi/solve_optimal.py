"""
GIẢI CO-2201-00249 - PHIÊN BẢN TỐI ƯU NHẤT
Tồn kho tối thiểu, hao hụt tối thiểu
"""
import os
import random
from ortools.sat.python import cp_model

random.seed(42)

# ===================================================================
# DATA 
# ===================================================================
DATA_I3 = [
    ("PHOI-I3.1.1 (425mm)", 425, 100),
    ("PHOI-I3.1.2 (420mm)", 420, 300),
    ("PHOI-I3.1.4a (445mm)", 445, 200),
    ("PHOI-I3.1.4b (400mm)", 400, 200),
    ("PHOI-I3.1.4c (175mm)", 175, 200),
    ("PHOI-I3.2.1 (367mm)", 367, 300),  # Gộp 50+50+200
    ("PHOI-I3.2.2a (324mm)", 324, 200),
    ("PHOI-I3.2.2b (330mm)", 330, 200),
    ("PHOI-I3.2.3 (397mm)", 397, 200),
]

DATA_I5 = [
    ("PHOI-I5.1.1 (850mm)", 850, 100),
    ("PHOI-I5.1.2 (420mm)", 420, 600),
    ("PHOI-I5.1.4a (870mm)", 870, 200),
    ("PHOI-I5.1.4b (400mm)", 400, 700),
    ("PHOI-I5.1.4c (175mm)", 175, 600),
    ("PHOI-I5.2.1 (425mm)", 425, 200),
    ("PHOI-I5.2.4 (445mm)", 445, 400),
    ("PHOI-I5.3.1a (365mm)", 365, 200),
    ("PHOI-I5.3.1b (405mm)", 405, 100),
    ("PHOI-I5.3.1c (375mm)", 375, 100),
    ("PHOI-I5.3.2a (665mm)", 665, 200),
    ("PHOI-I5.3.2b (145mm)", 145, 400),
]

def generate_patterns(stock, lengths, max_waste_pct=0.30, num_samples=500000):
    n = len(lengths)
    min_used = int(stock * (1 - max_waste_pct))
    max_counts = [min(stock // (l + 1), 25) for l in lengths]
    
    patterns = set()
    
    # Patterns đơn
    for i in range(n):
        for qty in range(1, max_counts[i] + 1):
            combo = [0] * n
            combo[i] = qty
            total = qty * lengths[i] + qty + 10
            if min_used <= total <= stock:
                patterns.add(tuple(combo + [stock - total]))
    
    # Patterns kết hợp
    for _ in range(num_samples):
        combo = [0] * n
        total = 10
        for i in random.sample(range(n), random.randint(2, min(5, n))):
            max_q = min(max_counts[i], (stock - total) // (lengths[i] + 1))
            if max_q > 0:
                combo[i] = random.randint(1, max_q)
                total += combo[i] * (lengths[i] + 1)
        if sum(combo) > 0 and min_used <= total <= stock:
            patterns.add(tuple(combo + [stock - total]))
    
    return [list(p) for p in patterns]

def solve_with_target_surplus(patterns, demands, target_surplus, time_limit=120):
    """Giải với target surplus cố định"""
    model = cp_model.CpModel()
    np, nd = len(patterns), len(demands)
    
    x = [model.NewIntVar(0, sum(demands)*2, f'x_{j}') for j in range(np)]
    
    for i in range(nd):
        produced = sum(x[j] * patterns[j][i] for j in range(np))
        model.Add(produced >= demands[i])
        model.Add(produced <= demands[i] + target_surplus)
    
    # Minimize waste
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

def find_optimal_surplus(patterns, demands, time_limit=60):
    """Binary search để tìm surplus tối thiểu"""
    lo, hi = 0, 50
    best_result = None
    best_surplus = hi
    
    while lo <= hi:
        mid = (lo + hi) // 2
        result = solve_with_target_surplus(patterns, demands, mid, time_limit)
        
        if result:
            best_result = result
            best_surplus = mid
            hi = mid - 1
        else:
            lo = mid + 1
    
    return best_surplus, best_result

def solve_order(name, data, stock, time_limit=90):
    print(f"\n{'='*60}")
    print(f"GIẢI: {name} (Stock: {stock}mm)")
    print(f"{'='*60}")
    
    names = [d[0] for d in data]
    lengths = [d[1] for d in data]
    demands = [d[2] for d in data]
    
    print(f"   Số loại: {len(lengths)}, Tổng SL: {sum(demands):,}")
    
    # Generate patterns
    print(f"\n🔍 Tạo patterns...")
    patterns = generate_patterns(stock, lengths, max_waste_pct=0.35, num_samples=500000)
    print(f"   ✅ {len(patterns):,} patterns")
    
    # Check coverage
    for i, l in enumerate(lengths):
        count = sum(1 for p in patterns if p[i] > 0)
        if count == 0:
            print(f"   ❌ {l}mm: không có pattern!")
            return None
    
    # Find optimal surplus
    print(f"\n🎯 Tìm surplus tối thiểu...")
    min_surplus, result = find_optimal_surplus(patterns, demands, time_limit)
    
    if result:
        wp = (result['total_waste'] / (result['total_bars'] * stock)) * 100 if result['total_bars'] > 0 else 0
        print(f"\n✅ THÀNH CÔNG!")
        print(f"   Max surplus/loại: {min_surplus}")
        print(f"   Số cây: {result['total_bars']}")
        print(f"   Hao hụt: {result['total_waste']/1000:.2f}m ({wp:.2f}%)")
        print(f"   Tổng tồn: {sum(result['surplus'])}")
        
        print(f"\n📊 Chi tiết:")
        for i, (name, length, demand) in enumerate(zip(names, lengths, demands)):
            print(f"   {length:>4}mm: cần {demand:>4}, cắt {result['production'][i]:>4}, tồn {result['surplus'][i]:>2}")
        
        return {'name': name, 'stock': stock, 'names': names, 'lengths': lengths, 
                'demands': demands, 'result': result, 'min_surplus': min_surplus}
    else:
        print(f"\n❌ THẤT BẠI!")
        return None

if __name__ == "__main__":
    print("=" * 60)
    print("GIẢI CO-2201-00249 - TỐI ƯU TỒN KHO & HAO HỤT")
    print("=" * 60)
    
    results = []
    
    r1 = solve_order("CO-2201-00249-I3", DATA_I3, 6000, time_limit=90)
    if r1: results.append(r1)
    
    r2 = solve_order("CO-2201-00249-I5", DATA_I5, 9000, time_limit=90)
    if r2: results.append(r2)
    
    print("\n" + "=" * 60)
    print("TỔNG KẾT CUỐI CÙNG")
    print("=" * 60)
    
    if len(results) == 2:
        total_bars = sum(r['result']['total_bars'] for r in results)
        total_waste = sum(r['result']['total_waste'] for r in results)
        total_len = sum(r['result']['total_bars'] * r['stock'] for r in results)
        total_surplus = sum(sum(r['result']['surplus']) for r in results)
        
        print(f"\n📦 KẾT QUẢ TỐI ƯU:")
        print(f"   I3: {results[0]['result']['total_bars']} cây × 6000mm, max tồn {results[0]['min_surplus']}/loại")
        print(f"   I5: {results[1]['result']['total_bars']} cây × 9000mm, max tồn {results[1]['min_surplus']}/loại")
        print(f"\n   TỔNG: {total_bars} cây")
        print(f"   Hao hụt: {total_waste/1000:.2f}m ({(total_waste/total_len)*100:.2f}%)")
        print(f"   Tổng tồn kho: {total_surplus} đoạn")
        
        # Lưu file
        out = os.path.join(os.path.dirname(__file__), "docs", "KET_QUA_CO-2201-00249_OPTIMAL.txt")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        
        with open(out, 'w', encoding='utf-8') as f:
            f.write("KẾT QUẢ TỐI ƯU CẮT SẮT CO-2201-00249\n")
            f.write("=" * 50 + "\n\n")
            f.write(f"TỔNG: {total_bars} cây sắt\n")
            f.write(f"Hao hụt: {total_waste/1000:.2f}m ({(total_waste/total_len)*100:.2f}%)\n")
            f.write(f"Tổng tồn kho: {total_surplus} đoạn\n\n")
            
            for r in results:
                f.write(f"\n{'='*50}\n")
                f.write(f"{r['name']} (Stock {r['stock']}mm)\n")
                f.write(f"Số cây: {r['result']['total_bars']}, Max tồn/loại: {r['min_surplus']}\n")
                f.write(f"{'='*50}\n\n")
                
                f.write("Chi tiết:\n")
                for i, (name, length, demand) in enumerate(zip(r['names'], r['lengths'], r['demands'])):
                    prod = r['result']['production'][i]
                    surp = r['result']['surplus'][i]
                    f.write(f"  {length}mm: cần {demand}, cắt {prod}, tồn {surp}\n")
                
                f.write("\nKế hoạch cắt:\n")
                for idx, pu in enumerate(r['result']['patterns_used'], 1):
                    segs = ", ".join([f"{r['lengths'][i]}×{pu['p'][i]}" for i in range(len(pu['p'])) if pu['p'][i] > 0])
                    f.write(f"  P{idx}: {segs} | hao hụt {pu['w']}mm | ×{pu['c']} cây\n")
        
        print(f"\n💾 Đã lưu: {out}")
        
        # In kế hoạch cắt
        for r in results:
            print(f"\n📋 KẾ HOẠCH {r['name']}:")
            for idx, pu in enumerate(r['result']['patterns_used'][:10], 1):
                segs = ", ".join([f"{r['lengths'][i]}×{pu['p'][i]}" for i in range(len(pu['p'])) if pu['p'][i] > 0])
                print(f"   P{idx}: {segs} | {pu['w']}mm | ×{pu['c']}")
            if len(r['result']['patterns_used']) > 10:
                print(f"   ... +{len(r['result']['patterns_used'])-10} patterns")
    else:
        print(f"\n⚠️ Chỉ giải được {len(results)} lô!")
