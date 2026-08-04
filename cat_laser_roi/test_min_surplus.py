"""
Test nhanh để tìm giá trị max_surplus tối thiểu khả thi
"""
import random
from ortools.sat.python import cp_model

random.seed(42)

# Data I3
lengths = [445, 425, 420, 400, 397, 367, 330, 324, 175]
demands = [200, 100, 300, 200, 200, 300, 200, 200, 200]

STOCK = 6000
n = len(lengths)

print("Tạo patterns...")
patterns = set()

# Patterns đơn
for i in range(n):
    for qty in range(1, 20):
        combo = [0] * n
        combo[i] = qty
        total = qty * lengths[i] + qty + 10
        if 4200 <= total <= STOCK:
            patterns.add(tuple(combo + [STOCK - total]))

# Patterns kết hợp
for _ in range(500000):
    combo = [0] * n
    total = 10
    for i in random.sample(range(n), random.randint(2, 5)):
        max_q = min(20, (STOCK - total) // (lengths[i] + 1))
        if max_q > 0:
            combo[i] = random.randint(1, max_q)
            total += combo[i] * (lengths[i] + 1)
    if sum(combo) > 0 and 4200 <= total <= STOCK:
        patterns.add(tuple(combo + [STOCK - total]))

patterns = [list(p) for p in patterns]
print(f"Patterns: {len(patterns):,}")

# Kiểm tra coverage
for i, l in enumerate(lengths):
    count = sum(1 for p in patterns if p[i] > 0)
    print(f"  {l}mm: {count:,} patterns")

# Binary search cho max_surplus tối thiểu
print("\nTìm max_surplus tối thiểu...")
lo, hi = 0, 100
best = None

while lo <= hi:
    mid = (lo + hi) // 2
    
    model = cp_model.CpModel()
    x = [model.NewIntVar(0, 5000, f'x_{j}') for j in range(len(patterns))]
    
    for i in range(n):
        produced = sum(x[j] * patterns[j][i] for j in range(len(patterns)))
        model.Add(produced >= demands[i])
        model.Add(produced <= demands[i] + mid)
    
    model.Minimize(sum(x[j] * patterns[j][-1] for j in range(len(patterns))))
    
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 30
    status = solver.Solve(model)
    
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        bars = sum(solver.Value(x[j]) for j in range(len(patterns)))
        waste = sum(solver.Value(x[j]) * patterns[j][-1] for j in range(len(patterns)))
        surplus = [sum(solver.Value(x[j]) * patterns[j][i] for j in range(len(patterns))) - demands[i] for i in range(n)]
        
        print(f"  max_surplus={mid}: ✅ {bars} bars, waste {waste/1000:.2f}m, surplus {surplus}")
        best = mid
        hi = mid - 1
    else:
        print(f"  max_surplus={mid}: ❌ INFEASIBLE")
        lo = mid + 1

print(f"\n🎯 Giá trị max_surplus tối thiểu khả thi: {best}")
