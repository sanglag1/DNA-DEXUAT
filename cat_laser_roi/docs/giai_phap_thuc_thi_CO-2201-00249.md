# Giải pháp thực thi CO-2201-00249

## Tổng quan vấn đề

Đơn hàng CO-2201-00249 có **23 dòng** với nhiều loại đoạn sắt từ **145mm đến 870mm**. Khi chạy qua thuật toán tối ưu hiện tại (Phase 1 + Phase 2), hệ thống báo **"Không tìm thấy lời giải"**.

### Nguyên nhân gốc

1. **Số tổ hợp quá lớn**: Với 16+ chiều dài khác nhau (sau khi gộp), số tổ hợp patterns lên tới hàng nghìn tỷ (`10^21`)
2. **Thuật toán CP-SAT enumerate_all_solutions không đảm bảo coverage**: Chỉ liệt kê một số nghiệm dựa trên thứ tự tìm kiếm
3. **Ràng buộc `produced >= demand` là ràng buộc cứng**: Nếu một loại đoạn không xuất hiện trong patterns → Phase 2 INFEASIBLE

---

## Giải pháp

### Bước 1: Chia đơn hàng thành 2 lô

Đơn hàng được chia theo mã sản phẩm:

| Lô | Mã sản phẩm | Stock Length | Số loại đoạn |
|----|-------------|--------------|--------------|
| **I3** | PHOI-I3.x.x | 6000mm | 9 loại |
| **I5** | PHOI-I5.x.x | 9000mm | 12 loại |

**Lý do**: Giảm độ phức tạp tổ hợp từ `O(n^16)` xuống `O(n^9)` và `O(n^12)`.

### Bước 2: Tạo patterns bằng Random Sampling

Thay vì duyệt tất cả tổ hợp (brute-force), sử dụng **Random Sampling** với chiến lược:

```python
# 1. Tạo patterns ĐƠN (đảm bảo coverage)
for i in range(num_segments):
    for qty in range(1, max_qty):
        pattern = [0] * num_segments
        pattern[i] = qty
        if is_valid(pattern):
            patterns.add(pattern)

# 2. Tạo patterns KẾT HỢP (random sampling)
for _ in range(500000):
    pattern = random_combination(2-5 loại đoạn)
    if is_valid(pattern):
        patterns.add(pattern)
```

**Kết quả**: Tạo được 100,000-300,000 patterns với **FULL coverage** cho tất cả các loại đoạn.

### Bước 3: Tối ưu với Binary Search

Sử dụng **Binary Search** để tìm giá trị `max_surplus` tối thiểu:

```python
lo, hi = 0, 50
while lo <= hi:
    mid = (lo + hi) // 2
    result = solve_with_constraint(max_surplus=mid)
    if result:
        best = mid
        hi = mid - 1
    else:
        lo = mid + 1
```

**Kết quả**: Tìm được `max_surplus = 0` (không tồn kho) là khả thi!

### Bước 4: Giải Phase 2 với OR-Tools CP-SAT

```python
model = cp_model.CpModel()

# Biến: số lần dùng mỗi pattern
x = [model.NewIntVar(0, max_bars, f'x_{j}') for j in range(num_patterns)]

# Ràng buộc: đáp ứng đúng nhu cầu (không thừa)
for i in range(num_segments):
    produced = sum(x[j] * patterns[j][i] for j in range(num_patterns))
    model.Add(produced >= demands[i])
    model.Add(produced <= demands[i] + max_surplus)

# Mục tiêu: tối thiểu hao hụt
model.Minimize(total_waste)
```

---

## Kết quả cuối cùng

| Chỉ số | Giá trị |
|--------|---------|
| **Tổng số cây sắt** | **306 cây** |
| **Hao hụt** | **164.44m (6.95%)** |
| **Tổng tồn kho** | **0 đoạn** ✅ |

### Chi tiết theo lô

| Lô | Stock | Số cây | Số loại pattern |
|----|-------|--------|-----------------|
| I3 | 6000mm | 129 cây | 110 patterns |
| I5 | 9000mm | 177 cây | 22 patterns |

---

## Scripts đã tạo

| File | Mô tả |
|------|-------|
| `solve_optimal.py` | Solver cuối cùng với Binary Search + Random Sampling |
| `solve_random.py` | Solver dùng Random Sampling (hao hụt 0%, tồn kho cao) |
| `test_min_surplus.py` | Test tìm giá trị max_surplus tối thiểu |

---

## Hướng dẫn sử dụng lại

1. **Chuẩn bị dữ liệu**: Chia đơn hàng theo nhóm sản phẩm (stock length tương đồng)

2. **Chạy solver**:
   ```bash
   python cat_laser_roi/solve_optimal.py
   ```

3. **Kết quả**: File `KET_QUA_CO-2201-00249_OPTIMAL.txt` trong thư mục `docs/`

---

## Bài học kinh nghiệm

1. **Đơn hàng lớn (>15 loại đoạn)** cần chia nhỏ trước khi tối ưu
2. **Random Sampling** hiệu quả hơn brute-force cho bài toán combinatorial lớn
3. **Binary Search** giúp tìm nhanh tham số tối ưu (max_surplus)
4. **Tồn kho = 0** là khả thi nếu có đủ đa dạng patterns

---

*Tài liệu tạo ngày: 26/01/2026*
