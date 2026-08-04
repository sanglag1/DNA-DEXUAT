# Thuật toán tối ưu cắt sắt - Phương pháp 2 (Advanced)

> **Mục đích**: Giải quyết các đơn hàng phức tạp mà phương pháp 1 (enumerate_all_solutions) không xử lý được.

## 1. Khi nào cần dùng Phương pháp 2?

| Điều kiện | Phương pháp 1 | Phương pháp 2 |
|-----------|---------------|---------------|
| Số loại đoạn | ≤ 12 loại | > 12 loại |
| Kết quả PM1 | Tìm được nghiệm | "Không tìm thấy lời giải" |
| Yêu cầu tồn kho | Cho phép tồn cao | Cần tồn kho = 0 hoặc rất thấp |

---

## 2. Tổng quan thuật toán

```
┌─────────────────────────────────────────────────────────┐
│  INPUT: segments[], demands[], stock_length            │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│  BƯỚC 1: Tiền xử lý                                     │
│  - Gộp các đoạn cùng chiều dài                          │
│  - Sắp xếp theo chiều dài giảm dần                      │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│  BƯỚC 2: Tạo patterns bằng Random Sampling              │
│  - Tạo patterns đơn (đảm bảo coverage)                  │
│  - Tạo patterns kết hợp (random sampling)              │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│  BƯỚC 3: Binary Search tìm max_surplus tối thiểu        │
│  - lo=0, hi=50                                          │
│  - Tìm giá trị nhỏ nhất mà bài toán có nghiệm           │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│  BƯỚC 4: Giải Phase 2 với OR-Tools CP-SAT               │
│  - Minimize waste                                       │
│  - Subject to: demand ≤ produced ≤ demand + max_surplus │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│  OUTPUT: cutting_plan[], total_bars, waste_percentage   │
└─────────────────────────────────────────────────────────┘
```

---

## 3. Chi tiết từng bước

### 3.1. Tiền xử lý dữ liệu

```python
def merge_by_length(data):
    """
    Gộp các đoạn có cùng chiều dài lại với nhau.
    
    Input:
        data = [
            ("PHOI-I3.2.1", 367, 50),
            ("PHOI-I3.2.1", 367, 50),
            ("PHOI-I3.2.3", 367, 200),
        ]
    
    Output:
        [
            {'length': 367, 'total_qty': 300, 'items': [...]},
        ]
    """
    merged = {}
    for name, length, qty in data:
        if length not in merged:
            merged[length] = {'length': length, 'total_qty': 0, 'items': []}
        merged[length]['total_qty'] += qty
        merged[length]['items'].append((name, qty))
    
    # Sắp xếp theo chiều dài giảm dần (ưu tiên đoạn dài)
    return sorted(merged.values(), key=lambda x: -x['length'])
```

### 3.2. Tạo patterns bằng Random Sampling

```python
import random

def generate_patterns(stock_length, piece_lengths, max_waste_pct=0.30, 
                      num_samples=500000, kerf_width=1, trim_start=10):
    """
    Tạo patterns bằng random sampling thay vì enumerate_all_solutions.
    
    Đảm bảo:
    - Mỗi loại đoạn đều có ít nhất 1 pattern chứa nó (coverage)
    - Đủ đa dạng patterns để tối ưu
    
    Parameters:
        stock_length: Chiều dài cây sắt (mm)
        piece_lengths: Danh sách chiều dài các đoạn cần cắt
        max_waste_pct: Hao hụt tối đa cho phép (0.30 = 30%)
        num_samples: Số lượng samples random
        kerf_width: Độ rộng lưỡi cắt (mm)
        trim_start: Phần tề đầu (mm)
    
    Returns:
        List[List[int]]: Mỗi pattern là [qty_0, qty_1, ..., qty_n, waste]
    """
    n = len(piece_lengths)
    min_used = int(stock_length * (1 - max_waste_pct))
    max_counts = [min(stock_length // (l + kerf_width), 25) for l in piece_lengths]
    
    patterns = set()
    
    # ============================================
    # BƯỚC 2.1: Tạo patterns ĐƠN (1 loại đoạn)
    # Đảm bảo TỪNG loại đoạn đều có pattern
    # ============================================
    for i in range(n):
        for qty in range(1, max_counts[i] + 1):
            combo = [0] * n
            combo[i] = qty
            
            total_used = qty * piece_lengths[i] + qty * kerf_width + trim_start
            
            if min_used <= total_used <= stock_length:
                waste = stock_length - total_used
                patterns.add(tuple(combo + [waste]))
    
    # ============================================
    # BƯỚC 2.2: Tạo patterns KẾT HỢP (2-5 loại)
    # Random sampling để có đủ đa dạng
    # ============================================
    for _ in range(num_samples):
        # Chọn ngẫu nhiên 2-5 loại đoạn
        num_types = random.randint(2, min(5, n))
        selected_indices = random.sample(range(n), num_types)
        
        combo = [0] * n
        total_used = trim_start
        
        for idx in selected_indices:
            # Tính số lượng tối đa có thể thêm
            max_qty = min(
                max_counts[idx],
                (stock_length - total_used) // (piece_lengths[idx] + kerf_width)
            )
            if max_qty > 0:
                qty = random.randint(1, max_qty)
                combo[idx] = qty
                total_used += qty * (piece_lengths[idx] + kerf_width)
        
        # Kiểm tra ràng buộc
        if sum(combo) > 0 and min_used <= total_used <= stock_length:
            waste = stock_length - total_used
            patterns.add(tuple(combo + [waste]))
    
    # Chuyển thành list và sắp xếp theo waste tăng dần
    result = [list(p) for p in patterns]
    result.sort(key=lambda x: x[-1])
    
    return result
```

### 3.3. Binary Search tìm max_surplus tối thiểu

```python
def find_optimal_surplus(patterns, demands, time_limit_per_try=60):
    """
    Tìm giá trị max_surplus nhỏ nhất mà bài toán có nghiệm.
    
    Parameters:
        patterns: List patterns từ bước 2
        demands: List số lượng cần của từng loại đoạn
        time_limit_per_try: Timeout cho mỗi lần thử (giây)
    
    Returns:
        (min_surplus, result): Surplus tối thiểu và kết quả tối ưu
    """
    lo, hi = 0, 50
    best_surplus = hi
    best_result = None
    
    while lo <= hi:
        mid = (lo + hi) // 2
        
        result = solve_with_surplus_constraint(patterns, demands, mid, time_limit_per_try)
        
        if result is not None:
            # Tìm được nghiệm, thử giảm surplus
            best_surplus = mid
            best_result = result
            hi = mid - 1
        else:
            # Không có nghiệm, tăng surplus
            lo = mid + 1
    
    return best_surplus, best_result
```

### 3.4. Giải Phase 2 với OR-Tools CP-SAT

```python
from ortools.sat.python import cp_model

def solve_with_surplus_constraint(patterns, demands, max_surplus, time_limit):
    """
    Giải bài toán Integer Programming với ràng buộc surplus.
    
    Mục tiêu: Minimize tổng hao hụt
    Ràng buộc:
        - produced[i] >= demands[i]  (đủ nhu cầu)
        - produced[i] <= demands[i] + max_surplus  (không thừa quá nhiều)
    
    Parameters:
        patterns: List[List[int]] - mỗi pattern là [qty_0, ..., qty_n, waste]
        demands: List[int] - số lượng cần của từng loại đoạn
        max_surplus: int - tồn kho tối đa cho phép mỗi loại
        time_limit: int - timeout (giây)
    
    Returns:
        dict hoặc None nếu không có nghiệm
    """
    model = cp_model.CpModel()
    
    num_patterns = len(patterns)
    num_segments = len(demands)
    
    # Biến quyết định: số lần sử dụng mỗi pattern
    max_bars = sum(demands) * 2  # Ước lượng upper bound
    x = [model.NewIntVar(0, max_bars, f'x_{j}') for j in range(num_patterns)]
    
    # Ràng buộc: Đáp ứng nhu cầu và giới hạn tồn kho
    for i in range(num_segments):
        # Tổng sản lượng loại i từ tất cả patterns
        produced = sum(x[j] * patterns[j][i] for j in range(num_patterns))
        
        # Phải đủ nhu cầu
        model.Add(produced >= demands[i])
        
        # Không được thừa quá max_surplus
        model.Add(produced <= demands[i] + max_surplus)
    
    # Mục tiêu: Tối thiểu hóa tổng hao hụt
    # waste nằm ở vị trí cuối của mỗi pattern (patterns[j][-1])
    total_waste = sum(x[j] * patterns[j][-1] for j in range(num_patterns))
    model.Minimize(total_waste)
    
    # Giải
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    
    status = solver.Solve(model)
    
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        # Thu thập kết quả
        result = {
            'patterns_used': [],
            'total_bars': 0,
            'total_waste': 0,
            'production': [0] * num_segments,
            'surplus': [0] * num_segments
        }
        
        for j in range(num_patterns):
            count = solver.Value(x[j])
            if count > 0:
                pattern = patterns[j]
                result['patterns_used'].append({
                    'pattern': pattern[:-1],  # Bỏ waste
                    'count': count,
                    'waste_mm': pattern[-1]
                })
                result['total_bars'] += count
                result['total_waste'] += count * pattern[-1]
                
                for i in range(num_segments):
                    result['production'][i] += count * pattern[i]
        
        for i in range(num_segments):
            result['surplus'][i] = result['production'][i] - demands[i]
        
        return result
    
    return None  # Không có nghiệm
```

---

## 4. Hàm main hoàn chỉnh

```python
def optimize_cutting_advanced(segments_data, stock_length, 
                               max_waste_pct=0.30, 
                               time_limit=300):
    """
    Hàm chính để tối ưu cắt sắt theo Phương pháp 2.
    
    Parameters:
        segments_data: List[(name, length, quantity)]
            Ví dụ: [("PHOI-I3.1.1", 425, 100), ...]
        
        stock_length: int
            Chiều dài cây sắt gốc (mm)
        
        max_waste_pct: float
            Hao hụt tối đa cho phép khi tạo patterns (0.30 = 30%)
        
        time_limit: int
            Timeout tổng (giây)
    
    Returns:
        dict: {
            'success': bool,
            'total_bars': int,
            'total_waste_mm': int,
            'waste_percentage': float,
            'total_surplus': int,
            'max_surplus_per_segment': int,
            'segments_detail': [...],
            'cutting_plan': [...]
        }
    """
    import random
    random.seed(42)  # Reproducible
    
    # 1. Tiền xử lý
    merged = merge_by_length(segments_data)
    piece_lengths = [m['length'] for m in merged]
    demands = [m['total_qty'] for m in merged]
    
    print(f"📊 Số loại đoạn (sau gộp): {len(piece_lengths)}")
    print(f"📊 Tổng số lượng: {sum(demands):,}")
    
    # 2. Tạo patterns
    print("\n🔍 Tạo patterns bằng Random Sampling...")
    patterns = generate_patterns(
        stock_length, piece_lengths, 
        max_waste_pct=max_waste_pct,
        num_samples=500000
    )
    print(f"✅ Tạo được {len(patterns):,} patterns")
    
    # Kiểm tra coverage
    for i, length in enumerate(piece_lengths):
        coverage = sum(1 for p in patterns if p[i] > 0)
        if coverage == 0:
            return {
                'success': False,
                'error': f'Đoạn {length}mm không có pattern nào!'
            }
    
    # 3. Binary search tìm max_surplus tối thiểu
    print("\n🎯 Tìm max_surplus tối thiểu...")
    time_per_try = min(60, time_limit // 10)
    min_surplus, result = find_optimal_surplus(patterns, demands, time_per_try)
    
    if result is None:
        return {
            'success': False,
            'error': 'Không tìm được nghiệm với max_surplus <= 50'
        }
    
    # 4. Tính kết quả
    total_length_used = result['total_bars'] * stock_length
    waste_pct = (result['total_waste'] / total_length_used) * 100
    
    return {
        'success': True,
        'total_bars': result['total_bars'],
        'total_waste_mm': result['total_waste'],
        'waste_percentage': round(waste_pct, 2),
        'total_surplus': sum(result['surplus']),
        'max_surplus_per_segment': min_surplus,
        'segments_detail': [
            {
                'length': merged[i]['length'],
                'items': merged[i]['items'],
                'demand': demands[i],
                'produced': result['production'][i],
                'surplus': result['surplus'][i]
            }
            for i in range(len(merged))
        ],
        'cutting_plan': [
            {
                'pattern_id': idx + 1,
                'segments': [
                    {'length': piece_lengths[i], 'quantity': pu['pattern'][i]}
                    for i in range(len(piece_lengths))
                    if pu['pattern'][i] > 0
                ],
                'waste_mm': pu['waste_mm'],
                'bar_count': pu['count']
            }
            for idx, pu in enumerate(result['patterns_used'])
        ]
    }
```

---

## 5. Ví dụ sử dụng

```python
# Dữ liệu đầu vào
segments = [
    ("PHOI-I3.1.1", 425, 100),
    ("PHOI-I3.1.2", 420, 300),
    ("PHOI-I3.1.4", 445, 200),
    ("PHOI-I3.1.4", 400, 200),
    ("PHOI-I3.1.4", 175, 200),
    ("PHOI-I3.2.1", 367, 300),  # Đã gộp 50+50+200
    ("PHOI-I3.2.2", 324, 200),
    ("PHOI-I3.2.2", 330, 200),
    ("PHOI-I3.2.3", 397, 200),
]

# Chạy tối ưu
result = optimize_cutting_advanced(
    segments_data=segments,
    stock_length=6000,
    max_waste_pct=0.30,
    time_limit=300
)

# Kết quả
if result['success']:
    print(f"✅ Số cây: {result['total_bars']}")
    print(f"✅ Hao hụt: {result['waste_percentage']}%")
    print(f"✅ Tồn kho max/loại: {result['max_surplus_per_segment']}")
else:
    print(f"❌ {result['error']}")
```

---

## 6. Cấu trúc output JSON

```json
{
  "success": true,
  "total_bars": 129,
  "total_waste_mm": 85420,
  "waste_percentage": 11.04,
  "total_surplus": 0,
  "max_surplus_per_segment": 0,
  "segments_detail": [
    {
      "length": 445,
      "items": [["PHOI-I3.1.4", 200]],
      "demand": 200,
      "produced": 200,
      "surplus": 0
    }
  ],
  "cutting_plan": [
    {
      "pattern_id": 1,
      "segments": [
        {"length": 420, "quantity": 9},
        {"length": 367, "quantity": 4},
        {"length": 330, "quantity": 1},
        {"length": 397, "quantity": 1}
      ],
      "waste_mm": 0,
      "bar_count": 1
    }
  ]
}
```

---

## 7. Dependencies

```
ortools>=9.0.0
```

Cài đặt:
```bash
pip install ortools
```

---

## 8. Lưu ý khi tích hợp vào ERPNext

1. **Trigger**: Gọi Phương pháp 2 khi Phương pháp 1 trả về lỗi "Không tìm thấy lời giải"

2. **Split logic**: Nếu đơn hàng có nhiều stock_length khác nhau, tự động chia thành các lô riêng

3. **Timeout**: Đặt timeout hợp lý (5-10 phút) vì thuật toán này chạy lâu hơn PM1

4. **Random seed**: Set `random.seed(42)` để kết quả reproducible

---

*Tài liệu phiên bản 1.0 - 26/01/2026*
