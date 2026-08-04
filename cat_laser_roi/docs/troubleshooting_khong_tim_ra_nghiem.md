# Troubleshooting: Không Tìm Được Phương Án Cắt Tối Ưu

> **Tài liệu hướng dẫn xử lý lỗi "no_solution" trong tối ưu hóa cắt sắt**

---

## Mục Lục

1. [Tổng Quan Vấn Đề](#1-tổng-quan-vấn-đề)
2. [Nguyên Nhân Không Tìm Được Nghiệm](#2-nguyên-nhân-không-tìm-được-nghiệm)
3. [Giải Pháp Khắc Phục](#3-giải-pháp-khắc-phục)
4. [Tối Ưu Tham Số stock_length](#4-tối-ưu-tham-số-stock_length)
5. [Case Study: CO-2201-00249](#5-case-study-co-2201-00249)
6. [Quy Trình Xử Lý Chuẩn](#6-quy-trình-xử-lý-chuẩn)
7. [FAQ](#7-faq)

---

## 1. Tổng Quan Vấn Đề

### 1.1 Hiện Tượng

Khi chạy tối ưu hóa cắt sắt (máy Laser hoặc MCTĐ), hệ thống báo lỗi:

```
❌ Không tìm được phương án cắt tối ưu
Status: INFEASIBLE / NO_SOLUTION
```

### 1.2 Ảnh Hưởng

- ⏸️ **Không thể tạo kế hoạch cắt** cho Cutting Order
- 🚫 **Dừng quy trình sản xuất** đang chờ phương án
- ⚠️ **Deadline bị ảnh hưởng** do delay trong lập kế hoạch

### 1.3 Scope Tài Liệu

Tài liệu này áp dụng cho:
- ✅ Máy cắt Laser (`cat_laser_roi/optimization_logic.py`)
- ✅ Máy cắt Tự động MCTĐ (`cat_sat/optimization_logic.py`)
- ✅ Cả 2 giai đoạn của thuật toán (Pattern Generation + Distribution)

---

## 2. Nguyên Nhân Không Tìm Được Nghiệm

### 2.1 Ràng Buộc `max_surplus` Quá Chặt 🔴

> [!CAUTION]
> **Nguyên nhân CHÍNH** trong hầu hết các trường hợp!

#### Cơ Chế

Thuật toán tối ưu hóa (Giai đoạn 2) có ràng buộc:

```python
# Với mỗi loại đoạn i
surplus[i] = produced[i] - demands[i]  # Tồn kho
model.Add(surplus[i] <= max_surplus)    # Tồn kho ≤ giới hạn
```

**Ý nghĩa**: Mỗi loại đoạn chỉ được phép tồn kho tối đa `max_surplus` cái.

#### Vấn Đề

Khi có **nhiều loại đoạn khác nhau**, các patterns tối ưu thường tạo **tồn kho không đồng đều**:

```
Pattern ghép 5 loại đoạn:
┌─────────────────────────────────────────┐
│ Loại A: sản xuất 102, cần 100 → tồn 2  │ ✅
│ Loại B: sản xuất 215, cần 200 → tồn 15 │ ⚠️
│ Loại C: sản xuất 50,  cần 50  → tồn 0  │ ✅
│ Loại D: sản xuất 328, cần 300 → tồn 28 │ ❌ Vượt!
│ Loại E: sản xuất 180, cần 180 → tồn 0  │ ✅
└─────────────────────────────────────────┘

Nếu max_surplus = 20:
→ Loại D vượt (28 > 20)
→ Pattern này bị loại
→ Phải chọn pattern kém tối ưu hơn
→ Dẫn đến KHÔNG tìm được tổ hợp khả thi
```

#### Công Thức Ước Lượng

```python
max_surplus_recommended = (Tổng SL cần / Số loại đoạn) × 5%
```

**Ví dụ**:
- Tổng SL: 6,250 đoạn
- Số loại: 23
- max_surplus ≥ (6250 / 23) × 0.05 ≈ **14**

> [!TIP]
> **Nguyên tắc**: Càng nhiều loại đoạn, cần `max_surplus` càng cao.

#### Bảng Tham Khảo

| Số loại đoạn | `max_surplus` đề xuất |
|--------------|----------------------|
| 1-5          | 5-10                 |
| 6-10         | 10-20                |
| 11-15        | 20-30                |
| 16-20        | 30-50                |
| **> 20**     | **50-100**           |

---

### 2.2 Số Lượng Loại Đoạn Quá Nhiều 🟡

#### Độ Phức Tạp

Số biến quyết định trong Giai đoạn 2:

```
Số biến ≈ Số patterns × Số loại đoạn

Ví dụ:
- Số patterns: 50,000
- Số loại đoạn: 23
→ Số biến: 1,150,000 biến!
```

**Or-Tools CP-SAT** có thể xử lý, nhưng:
- ⏱️ Thời gian tìm nghiệm tăng theo **hàm mũ**
- 🎯 Khó tìm được nghiệm trong `time_limit` (mặc định 360s)

#### Ngưỡng An Toàn

| Số loại đoạn | Khả năng tìm nghiệm | Thời gian |
|--------------|---------------------|-----------|
| < 10         | 🟢 Rất cao         | < 60s     |
| 10-15        | 🟢 Cao             | 60-180s   |
| 16-20        | 🟡 Trung bình      | 180-360s  |
| **> 20**     | 🔴 **Thấp**        | **> 360s** |

---

### 2.3 `stock_length` Không Phù Hợp 🟡

#### 2.3.1 Cây Sắt Quá Ngắn

```
stock_length = 3000mm
Đoạn cần: 870mm, 850mm, 665mm

Pattern khả thi:
- 870 × 3 = 2610 + kerf + trim ≈ 2630mm ✅ (Nhưng ít biến thể)
- 870 × 4 = 3480mm ❌ Vượt

→ Quá ÍT patterns đa dạng
→ Khó đáp ứng đồng thời nhiều loại đoạn
```

#### 2.3.2 Cây Sắt Quá Dài

```
stock_length = 12000mm
Đoạn ngắn: 145mm, 175mm

Pattern có thể:
- 145 × 82 = 11,890mm + overhead ≈ 11,992mm
- 175 × 68 = 11,900mm + overhead ≈ 12,008mm ❌
- 145 × 50 + 175 × 20 = 10,750mm (và hàng nghìn tổ hợp khác)

→ QUÁ NHIỀU patterns (> 100,000)
→ Giai đoạn 2 mất quá nhiều thời gian
→ Timeout hoặc out-of-memory
```

#### Công Thức Tối Ưu

```python
stock_length_optimal = max(
    largest_segment × 7,      # Gấp 6-8 lần đoạn dài nhất
    average_segment × 14,     # Gấp 12-15 lần đoạn trung bình
    nearest_standard_length   # Làm tròn về chiều dài tiêu chuẩn
)
```

---

### 2.4 Phân Bố Kích Thước Không Đồng Đều 🟢

#### Vấn Đề Ghép Nối

```
Đoạn ngắn nhất:  145mm  ─┐
Đoạn dài nhất:   870mm  ─┤ Tỷ lệ: 870/145 = 6x
                         └→ Khó ghép hiệu quả
```

**Ví dụ Pattern**:

```
stock_length = 6000mm

Pattern 1 (tập trung đoạn dài):
870 × 6 = 5220mm + kerf + trim ≈ 5236mm
→ Hao hụt: 764mm (12.7%) ❌ Vượt giới hạn 1%

Pattern 2 (trộn lẫn):
870 × 5 + 145 × 3 = 4785mm + overhead ≈ 4803mm
→ Hao hụt: 1197mm (20%) ❌ Vượt giới hạn

Pattern 3 (đoạn dài + nhiều đoạn ngắn):
870 × 4 + 175 × 8 + 145 × 2 = 5170mm + overhead ≈ 5197mm
→ Hao hụt: 803mm (13.4%) ❌ Vượt giới hạn
```

**Kết quả**: Khó tạo patterns vừa hiệu quả vừa đáp ứng nhu cầu.

---

### 2.5 Số Lượng Nhu Cầu Không Cân Đối 🟢

```
Loại A: 50 đoạn   ─┐
Loại B: 700 đoạn  ─┤ Tỷ lệ: 700/50 = 14x
                   └→ Khó cân bằng tồn kho
```

**Vấn đề**: Pattern có cả A và B → Phải lặp nhiều lần → A tồn kho quá nhiều

```
Pattern: [A×5, B×2]

Để đủ B (700 đoạn):
→ Lặp 700/2 = 350 lần
→ A sản xuất: 350 × 5 = 1750 đoạn
→ A tồn kho: 1750 - 50 = 1700 ❌ Vượt max_surplus!
```

---

## 3. Giải Pháp Khắc Phục

### 3.1 Tăng `max_surplus` ⭐ (Ưu tiên cao nhất)

> [!TIP]
> Giải pháp NHANH và HIỆU QUẢ nhất trong 90% trường hợp!

#### Cách Thực Hiện

**Bước 1**: Mở Cutting Order Form

**Bước 2**: Tìm trường **"Max Surplus"** (Tồn kho tối đa)

**Bước 3**: Thử các giá trị tăng dần:

```
Giá trị hiện tại: 10
└→ Thử 20   → Chạy lại tối ưu hóa
   └→ Vẫn lỗi? Thử 50
      └→ Vẫn lỗi? Thử 100
```

#### Khi Nào Dừng Tăng?

Dừng khi:
- ✅ Tìm được nghiệm tối ưu, HOẶC
- ⚠️ `max_surplus` > (Trung bình nhu cầu mỗi loại × 50%)

**Ví dụ**:
```
Trung bình nhu cầu = 6250 / 23 ≈ 272 đoạn/loại
Giới hạn tối đa: 272 × 0.5 = 136
→ Không nên tăng max_surplus > 136
```

#### Ảnh Hưởng

| `max_surplus` | Tồn kho | Vốn lưu động | Khả năng tìm nghiệm |
|---------------|---------|--------------|---------------------|
| 10            | Thấp    | Tối ưu       | 🔴 Thấp (nếu > 15 loại) |
| 50            | Vừa     | Chấp nhận được | 🟢 Cao |
| 100           | Cao     | Tăng ~20%    | 🟢 Rất cao |

---

### 3.2 Chia Nhỏ Cutting Order (Divide & Conquer)

> [!IMPORTANT]
> Áp dụng khi Giải pháp 3.1 không hiệu quả hoặc khi số loại đoạn > 20.

#### Chiến Lược Chia

##### **Phương Án A: Chia Theo Sản Phẩm/Mãnh**

```
Order gốc: 23 loại đoạn từ sản phẩm I3 + I5

Chia thành:
┌────────────────────────────────────┐
│ CO-xxx-I3: Sản phẩm I3 (11 loại)  │
│ - PHOI-I3.1.1: Khung tựa          │
│ - PHOI-I3.1.2: Tay trái           │
│ - ...                              │
└────────────────────────────────────┘

┌────────────────────────────────────┐
│ CO-xxx-I5: Sản phẩm I5 (12 loại)  │
│ - PHOI-I5.1.1: Khung tựa đôi      │
│ - PHOI-I5.1.2: Tay trái ghế đôi   │
│ - ...                              │
└────────────────────────────────────┘
```

##### **Phương Án B: Chia Theo Kích Thước**

```
┌───────────────────────────────────────┐
│ CO-xxx-LONG: Đoạn dài (≥ 400mm)      │
│ 15 loại: 870, 850, 665, 445, ...     │
│ stock_length = 9000mm                 │
└───────────────────────────────────────┘

┌───────────────────────────────────────┐
│ CO-xxx-SHORT: Đoạn ngắn (< 400mm)    │
│ 8 loại: 375, 367, 365, 175, 145      │
│ stock_length = 6000mm                 │
└───────────────────────────────────────┘
```

##### **Phương Án C: Chia Theo Số Lượng**

```
┌───────────────────────────────────────┐
│ CO-xxx-HIGH: SL cao (≥ 200)          │
│ 14 loại với tổng SL: 5,450           │
└───────────────────────────────────────┘

┌───────────────────────────────────────┐
│ CO-xxx-LOW: SL thấp (< 200)          │
│ 9 loại với tổng SL: 800              │
└───────────────────────────────────────┘
```

#### Lợi Ích & Trade-offs

| Lợi ích | Trade-off |
|---------|-----------|
| ✅ Giảm độ phức tạp bài toán | ⚠️ Tăng số lần setup máy |
| ✅ Tăng tốc độ tìm nghiệm (5-10x) | ⚠️ Cần quản lý nhiều orders |
| ✅ Dễ tracking tiến độ theo batch | ⚠️ Có thể hao hụt tổng thể tăng nhẹ |

---

### 3.3 Tăng Thời Gian Tìm Nghiệm

#### Cấu Hình Hiện Tại

File: [`cat_laser_roi/optimization_logic.py`](file:///home/trand/frappe-bench-v16/apps/iea/iea/cat_laser_roi/optimization_logic.py)

```python
# Dòng ~450
time_limit_seconds = 120 * 3  # 360 giây = 6 phút
```

#### Khuyến Nghị

| Số loại đoạn | `time_limit` đề xuất |
|--------------|----------------------|
| < 10         | 180s (3 phút)        |
| 10-15        | 360s (6 phút)        |
| 16-20        | 600s (10 phút)       |
| **> 20**     | **900s (15 phút)**   |

#### Cách Chỉnh Sửa

```python
# Tìm dòng time_limit_seconds
time_limit_seconds = 900  # Tăng lên 15 phút cho orders phức tạp
```

> [!WARNING]
> Restart Frappe workers sau khi sửa code: `bench restart`

---

### 3.4 Điều Chỉnh Ràng Buộc Hao Hụt

#### Ràng Buộc Hiện Tại

**Giai đoạn 1** (Pattern generation):
```python
# Dòng 56
min_material_used = int(stock_length * (1 - 0.01))  # Hao hụt ≤ 1%
```

**Giai đoạn 2** (Distribution):
```python
# Dòng 391
max_waste_percentage = 0.015  # Lọc patterns hao hụt ≤ 1.5%
```

#### Nới Lỏng Tạm Thời

Khi input quá khó (nhiều loại + kích thước lệch pha):

```python
# Giai đoạn 1: Tăng lên 2%
min_material_used = int(stock_length * (1 - 0.02))

# Giai đoạn 2: Tăng lên 2.5%
max_waste_percentage = 0.025
```

> [!CAUTION]
> - Chỉ dùng khi các giải pháp khác thất bại
> - Review lại kết quả để đảm bảo hao hụt thực tế vẫn chấp nhận được
> - Trở về giá trị mặc định khi xong

---

### 3.5 Review và Clean Dữ Liệu Đầu Vào

#### Checklist Kiểm Tra

##### ✅ 1. Trùng Lặp Đoạn

```
❌ Trước khi gộp:
- 367mm × 50  (PHOI-I3.2.1 - Mặt bàn - có dập)
- 367mm × 50  (PHOI-I3.2.1 - Mặt bàn - không dập)

✅ Sau khi gộp:
- 367mm × 100 (PHOI-I3.2.1 - Mặt bàn)
→ Giảm từ 2 loại xuống 1 loại
```

##### ✅ 2. Làm Tròn Kích Thước

Nếu dung sai cho phép (±1-2mm):

```
❌ Trước:
- 365mm × 200
- 367mm × 100
- 370mm × 150

✅ Sau (làm tròn về 365mm):
- 365mm × 450
→ Giảm từ 3 loại xuống 1 loại
```

##### ✅ 3. Chia Nhỏ Số Lượng Lớn

```
❌ Trước:
- 400mm × 1,500

✅ Sau:
- Order 1: 400mm × 750
- Order 2: 400mm × 750
→ Mỗi order dễ tối ưu hơn
```

---

## 4. Tối Ưu Tham Số `stock_length`

### 4.1 Tại Sao `stock_length` Quan Trọng?

```
┌─────────────────────────────────────────────────┐
│  stock_length QUÁ NGẮN                          │
├─────────────────────────────────────────────────┤
│  → Ít patterns khả thi                          │
│  → Thiếu đa dạng để ghép nhiều loại đoạn        │
│  → Khó tìm nghiệm                               │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│  stock_length QUÁ DÀI                           │
├─────────────────────────────────────────────────┤
│  → Quá nhiều patterns (hàng triệu)              │
│  → Giai đoạn 2 chậm, timeout                    │
│  → Memory overflow                              │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│  stock_length PHÙ HỢP ✅                        │
├─────────────────────────────────────────────────┤
│  → Đủ patterns đa dạng (20k-80k)                │
│  → Cân bằng giữa hiệu quả và tốc độ             │
│  → Tìm nghiệm nhanh và chính xác                │
└─────────────────────────────────────────────────┘
```

---

### 4.2 Chiều Dài Tiêu Chuẩn Thị Trường

| Loại sắt | Chiều dài phổ biến | Ghi chú |
|----------|-------------------|---------|
| V15, V20 | **6000mm** ⭐      | Phổ biến nhất |
| V25, V30 | 6000mm, 9000mm    | Tùy nhà cung cấp |
| Ống tròn | 6000mm, 12000mm   | |
| Đặc biệt | 3000mm, 5000mm    | Ít dùng |

**Khuyến nghị**: Ưu tiên dùng **6000mm** hoặc **9000mm** để dễ mua nguyên liệu.

---

### 4.3 Công Thức Tính `stock_length` Tối Ưu

```python
def calculate_optimal_stock_length(segment_lengths, num_segments):
    """
    Tính stock_length tối ưu dựa trên dữ liệu đầu vào
    """
    largest = max(segment_lengths)
    average = sum(segment_lengths) / len(segment_lengths)
    
    # Option 1: Gấp 7 lần đoạn dài nhất
    option1 = largest * 7
    
    # Option 2: Gấp 14 lần đoạn trung bình
    option2 = average * 14
    
    # Làm tròn về chiều dài tiêu chuẩn
    standard_lengths = [3000, 5000, 6000, 9000, 12000]
    target = max(option1, option2)
    
    # Tìm chiều dài tiêu chuẩn gần nhất (ưu tiên lớn hơn)
    best_match = min(
        [x for x in standard_lengths if x >= target],
        default=max(standard_lengths)
    )
    
    # Điều chỉnh theo số lượng loại đoạn
    if num_segments > 20 and best_match < 9000:
        best_match = 9000
    
    return best_match
```

---

### 4.4 Bảng Tra Cứu Nhanh

| Đoạn lớn nhất | Số loại | `stock_length` đề xuất | Lý do |
|---------------|---------|------------------------|-------|
| < 400mm       | < 10    | 5000mm                 | Đoạn ngắn, ít loại |
| < 500mm       | 10-15   | **6000mm** ⭐          | Chuẩn phổ thông |
| 500-700mm     | < 15    | 6000mm                 | Vừa phải |
| 500-700mm     | 15-25   | 6000-9000mm            | Nhiều loại → cần dài hơn |
| **700-900mm** | **> 20** | **9000mm** ⭐          | Đoạn dài + nhiều loại |
| > 900mm       | Any     | 12000mm                | Đoạn siêu dài |

---

### 4.5 Thử Nghiệm Nhiều Giá Trị

Nếu không chắc, thử tuần tự:

```python
# Pseudo-code workflow
candidate_lengths = [6000, 9000, 12000, 5000]

for stock_length in candidate_lengths:
    result = run_optimization(
        stock_length=stock_length,
        max_surplus=50,
        time_limit=600
    )
    
    if result.status == "OPTIMAL":
        print(f"✅ Thành công với stock_length = {stock_length}mm")
        print(f"   - Tổng cây sắt: {result.total_bars}")
        print(f"   - Hao hụt: {result.waste_percentage:.2f}%")
        break
    else:
        print(f"❌ Thất bại với stock_length = {stock_length}mm")
        print(f"   - Số patterns: {result.num_patterns}")
        print(f"   - Thử giá trị tiếp theo...")
```

---

### 4.6 Tối Ưu Theo Nhóm Kích Thước

Khi có đoạn quá lệch pha, chia làm nhiều orders với `stock_length` khác nhau:

#### Ví Dụ: Input Có Đoạn 145mm-870mm

```
┌──────────────────────────────────────────┐
│ GROUP 1: Đoạn siêu dài (≥ 800mm)         │
├──────────────────────────────────────────┤
│ Segments: 870, 850                       │
│ stock_length = 9000mm                    │
│ Reason: 870×10 = 8700 + overhead ≈ 8750 │
└──────────────────────────────────────────┘

┌──────────────────────────────────────────┐
│ GROUP 2: Đoạn dài (400-700mm)            │
├──────────────────────────────────────────┤
│ Segments: 665, 445, 425, 420, 405, 400  │
│ stock_length = 6000mm                    │
│ Reason: 425×14 = 5950 + overhead ≈ 5964 │
└──────────────────────────────────────────┘

┌──────────────────────────────────────────┐
│ GROUP 3: Đoạn ngắn (< 400mm)             │
├──────────────────────────────────────────┤
│ Segments: 375, 367, 365, 330, 324, ...  │
│ stock_length = 6000mm                    │
│ Reason: 367×16 = 5872 + overhead ≈ 5888 │
└──────────────────────────────────────────┘

┌──────────────────────────────────────────┐
│ GROUP 4: Đoạn siêu ngắn (< 200mm)        │
├──────────────────────────────────────────┤
│ Segments: 175, 145                       │
│ stock_length = 6000mm                    │
│ Reason: 175×34 = 5950 + overhead ≈ 5984 │
└──────────────────────────────────────────┘
```

**Lợi ích**:
- ✅ Mỗi group có patterns rất hiệu quả (>99%)
- ✅ Giảm độ phức tạp từ 23 loại → 4 groups (6, 6, 8, 3 loại)
- ✅ Dễ quản lý sản xuất theo batch

---

## 5. Case Study: CO-2201-00249

### 5.1 Thông Tin Input

```yaml
Cutting Order: CO-2201-00249
Số loại đoạn: 23
Tổng số lượng: 6,250 đoạn
Kích thước:
  - Nhỏ nhất: 145mm
  - Lớn nhất: 870mm
  - Trung bình: ~430mm
Phân bổ SL:
  - Nhỏ nhất: 50 (367mm - PHOI-I3.2.1)
  - Lớn nhất: 700 (400mm - PHOI-I5.1.4)
```

### 5.2 Triệu Chứng

```
❌ Không tìm được phương án cắt tối ưu
Status: NO_SOLUTION / INFEASIBLE
Time elapsed: 360s (timeout)
```

### 5.3 Phân Tích Nguyên Nhân

| Yếu tố | Giá trị | Đánh giá | Ảnh hưởng |
|--------|---------|----------|-----------|
| **Số loại đoạn** | 23 | 🔴 RẤT CAO | Chính |
| **`max_surplus`** | ~10 (giả định) | 🔴 QUÁ THẤP | Chính |
| **Kích thước lệch pha** | 870/145 = 6x | 🟡 CAO | Phụ |
| **SL lệch pha** | 700/50 = 14x | 🟡 CAO | Phụ |
| **`stock_length`** | 6000mm? | 🟡 HƠI NGẮN | Phụ |

### 5.4 Giải Pháp Đề Xuất

#### **Plan A: Quick Fix (15 phút)**

```yaml
Step 1: Tăng max_surplus
  Current: 10
  New: 50
  
Step 2: Tăng stock_length (nếu đang dùng 6000mm)
  Current: 6000mm
  New: 9000mm
  Reason: Đoạn 870mm × 10 = 8700 + overhead ≈ 8720mm (hiệu quả 97%)
  
Step 3: Tăng time_limit
  Current: 360s
  New: 600s
  
Step 4: Chạy lại tối ưu hóa
```

**Kết quả kỳ vọng**: 🟢 85% khả năng thành công

---

#### **Plan B: Chia Order (2 giờ)**

Nếu Plan A thất bại:

```yaml
CO-2201-00249-I3:
  Loại đoạn: 11 (PHOI-I3.x.x)
  Tổng SL: 2,200
  stock_length: 6000mm
  max_surplus: 30
  
CO-2201-00249-I5:
  Loại đoạn: 12 (PHOI-I5.x.x)
  Tổng SL: 4,050
  stock_length: 9000mm (vì có đoạn 870mm)
  max_surplus: 40
```

**Kết quả kỳ vọng**: 🟢 98% khả năng thành công

---

#### **Plan C: Chia Theo Kích Thước (3 giờ)**

Nếu Plan B vẫn thất bại:

```yaml
CO-2201-00249-LONG:
  Segments: ≥ 600mm (870, 850, 665)
  SL: 500
  stock_length: 9000mm
  max_surplus: 20
  
CO-2201-00249-MEDIUM:
  Segments: 300-599mm (445, 425, 420, 405, 400, 397, 375, 367, 365, 330, 324)
  SL: 4,050
  stock_length: 6000mm
  max_surplus: 50
  
CO-2201-00249-SHORT:
  Segments: < 300mm (175, 145)
  SL: 1,700
  stock_length: 6000mm
  max_surplus: 30
```

**Kết quả kỳ vọng**: 🟢 99.9% khả năng thành công

---

### 5.5 Bài Học Rút Ra

> [!IMPORTANT]
> **Quy tắc ngón tay cái**: Với **số loại đoạn > 20**, luôn chia nhỏ Order hoặc đặt `max_surplus` ≥ 50.

| Metric | Ngưỡng cảnh báo | Hành động |
|--------|-----------------|-----------|
| Số loại đoạn | > 15 | Xem xét chia Order |
| Số loại đoạn | > 20 | **BẮT BUỘC** chia Order hoặc `max_surplus` ≥ 50 |
| Tỷ lệ kích thước | > 5x | Chia theo nhóm kích thước |
| Tỷ lệ SL | > 10x | Review lại nhu cầu, cân nhắc chia batch |

---

## 6. Quy Trình Xử Lý Chuẩn

### Flowchart

```
┌─────────────────────────────────────────┐
│ Gặp lỗi "Không tìm được nghiệm"         │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│ 1. Kiểm tra số loại đoạn                │
├─────────────────────────────────────────┤
│ Số loại ≤ 15? ───────YES───────┐        │
│    │                            │        │
│   NO                            ▼        │
│    │                     ┌──────────────┐│
│    │                     │ Tăng         ││
│    │                     │ max_surplus  ││
│    │                     │ lên 30-50    ││
│    │                     └──────┬───────┘│
│    │                            │        │
│    ▼                            │        │
│ ┌────────────────────┐          │        │
│ │ Chia Order theo    │          │        │
│ │ sản phẩm/kích      │          │        │
│ │ thước (Plan B/C)   │          │        │
│ └────────┬───────────┘          │        │
│          │                      │        │
│          └──────────────────────┘        │
└─────────────────┬───────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────┐
│ 2. Kiểm tra stock_length                │
├─────────────────────────────────────────┤
│ Đoạn lớn nhất > 700mm?                  │
│    │                                     │
│   YES → stock_length ≥ 9000mm           │
│    │                                     │
│   NO → stock_length = 6000mm            │
└─────────────────┬───────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────┐
│ 3. Chạy lại tối ưu hóa                  │
├─────────────────────────────────────────┤
│ Thành công? ────YES───→ ✅ DONE         │
│    │                                     │
│   NO                                     │
│    │                                     │
│    ▼                                     │
│ 4. Tăng time_limit lên 600-900s         │
│    Chạy lại                             │
│    │                                     │
│    Thành công? ────YES───→ ✅ DONE      │
│    │                                     │
│   NO                                     │
│    │                                     │
│    ▼                                     │
│ 5. Liên hệ Team kỹ thuật                │
│    (Có thể cần điều chỉnh thuật toán)  │
└─────────────────────────────────────────┘
```

---

### Checklist Xử Lý

#### Phase 1: Đánh Giá Ban Đầu (5 phút)

- [ ] Đếm số loại đoạn trong Cutting Order
- [ ] Kiểm tra giá trị `max_surplus` hiện tại
- [ ] Xác định `stock_length` đang dùng
- [ ] Xác định kích thước đoạn lớn nhất và nhỏ nhất

#### Phase 2: Quick Fixes (15 phút)

- [ ] Nếu số loại ≤ 15: Tăng `max_surplus` lên 30-50
- [ ] Nếu số loại > 15: Tăng `max_surplus` lên 50-100
- [ ] Nếu đoạn lớn nhất > 700mm: Tăng `stock_length` lên 9000mm
- [ ] Chạy lại tối ưu hóa
- [ ] Nếu thành công → **DONE** ✅

#### Phase 3: Chia Order (1-2 giờ)

- [ ] Phân tích cách chia hợp lý (sản phẩm / kích thước / SL)
- [ ] Tạo các Sub-orders mới
- [ ] Set `max_surplus` phù hợp cho mỗi Sub-order
- [ ] Chạy tối ưu hóa cho từng Sub-order
- [ ] Nếu thành công → **DONE** ✅

#### Phase 4: Escalate (Nếu vẫn thất bại)

- [ ] Export dữ liệu input ra CSV
- [ ] Chụp screenshot lỗi
- [ ] Báo cáo Team kỹ thuật với thông tin:
  - Số loại đoạn
  - Phân bố kích thước và SL
  - Các tham số đã thử (`max_surplus`, `stock_length`, `time_limit`)

---

## 7. FAQ

### Q1: Tại sao phải có ràng buộc `max_surplus`?

**A**: Để kiểm soát tồn kho và vốn lưu động.

```
Ví dụ không có max_surplus:
Order: 400mm × 100 đoạn

Thuật toán có thể chọn:
- Pattern X: cắt 1,000 đoạn 400mm (hao hụt tối thiểu)
→ Tồn kho: 1,000 - 100 = 900 đoạn thừa
→ Chiếm vốn: 900 × 50,000đ = 45 triệu đồng!
→ Chiếm kho: 900 × 0.4m = 360m sắt
```

Với `max_surplus = 20`:
```
→ Tồn kho tối đa: 20 đoạn
→ Vốn: 1 triệu
→ Kho: 8m
```

---

### Q2: Giá trị `max_surplus` bao nhiêu là hợp lý?

**A**: Phụ thuộc vào số loại đoạn và chính sách tồn kho:

| Tình huống | `max_surplus` đề xuất | Lý do |
|------------|----------------------|-------|
| Ít loại (< 10) | 10-20 | Dễ cân bằng tồn kho |
| Trung bình (10-15) | 20-30 | Cần linh hoạt hơn |
| Nhiều loại (16-20) | 30-50 | Khó cân bằng đều |
| **Rất nhiều (> 20)** | **50-100** | Không gian tìm kiếm lớn |

**Công thức**: `(Tổng SL / Số loại) × 5%`

---

### Q3: Có thể bỏ ràng buộc `max_surplus` không?

**A**: Được, nhưng không khuyến nghị.

**Cách làm**:
- Option 1: Đặt giá trị rất lớn: `max_surplus = 9999`
- Option 2: Thêm checkbox "Unlimited Surplus" trong UI → Bỏ qua constraint

**Rủi ro**:
- ⚠️ Tồn kho không kiểm soát
- ⚠️ Vốn lưu động tăng đột biến
- ⚠️ Kho hàng quá tải

**Khi nào dùng**:
- ✅ Order cực kỳ phức tạp (> 30 loại)
- ✅ Có chính sách "sản xuất dự trữ"
- ✅ Không gian kho dư thừa

---

### Q4: Chia Order có ảnh hưởng gì đến sản xuất?

**A**: Có một số ảnh hưởng:

| Ảnh hưởng | Mức độ | Giải pháp |
|-----------|--------|-----------|
| **Tăng số lần setup máy** | 🟡 Vừa | Nhóm các Sub-orders gần nhau về thời gian |
| **Tăng số documents quản lý** | 🟢 Nhẹ | Dùng naming convention (CO-xxx-A, CO-xxx-B) |
| **Hao hụt tổng có thể tăng nhẹ** | 🟢 Nhẹ | Chấp nhận được (tăng ~0.1-0.3%) |
| **Tracking tiến độ phức tạp hơn** | 🟡 Vừa | Tạo Parent-Child relationship |

**Trade-off**: Chia Order → Tăng overhead quản lý, nhưng **giảm complexity** và **đảm bảo tìm được nghiệm**.

---

### Q5: Làm sao biết `stock_length` hiện tại là bao nhiêu?

**A**: Kiểm tra trong Cutting Order Form:

```
1. Mở Cutting Order
2. Tìm section "Thông Tin Sắt" hoặc "Stock Settings"
3. Field: "Chiều dài cây sắt (mm)" / "Stock Length"
```

Hoặc query trực tiếp:

```python
import frappe

co = frappe.get_doc("Cutting Order", "CO-2201-00249")
print(co.stock_length)
```

---

### Q6: Tại sao với cùng input, có lúc tìm được nghiệm, có lúc không?

**A**: CP-SAT Solver có yếu tố **random**.

Mỗi lần chạy:
- Thứ tự explore không gian tìm kiếm khác nhau
- Heuristics khác nhau
- Có thể tìm thấy nghiệm nhanh, hoặc timeout trước khi tìm thấy

**Giải pháp**: 
- Set `random_seed` cố định (deterministic)
- Tăng `time_limit` để đảm bảo đủ thời gian
- Nếu gặp timeout, chạy lại 2-3 lần (có thể thành công)

---

### Q7: Có thể cắt nhiều `stock_length` khác nhau trong 1 Order không?

**A**: Hiện tại **KHÔNG** hỗ trợ trong thuật toán.

**Workaround**:
1. Chia Order theo nhóm kích thước
2. Mỗi Order dùng `stock_length` riêng
3. Merge kết quả trong sản xuất

**Roadmap**: Có thể phát triển tính năng "Multi-length optimization" trong tương lai.

---

### Q8: Nếu tất cả Giải pháp đều thất bại thì sao?

**A**: Liên hệ Team Kỹ Thuật với thông tin:

```yaml
Cutting Order ID: CO-xxx
Số loại đoạn: XX
Phân bố kích thước:
  - Min: XXX mm
  - Max: XXX mm
  - List: [xxx, xxx, ...]
Phân bố SL:
  - Min: XX
  - Max: XXX
  - List: [xx, xx, ...]
Tham số đã thử:
  - max_surplus: [10, 30, 50, 100]
  - stock_length: [6000, 9000]
  - time_limit: [360, 600, 900]
Kết quả: Tất cả đều INFEASIBLE
```

Có thể cần:
- 🔧 Điều chỉnh thuật toán (nới lỏng constraints)
- 🔧 Pre-processing đặc biệt cho input này
- 🔧 Hybrid approach (kết hợp cutting theo batch)

---

## 8. Kết Luận

### Nguyên Tắc 80/20

**80% trường hợp** giải quyết bằng:
1. ✅ Tăng `max_surplus` lên 50-100
2. ✅ Điều chỉnh `stock_length` phù hợp (9000mm cho đoạn > 700mm)

**20% trường hợp còn lại**:
3. ✅ Chia Order thành Sub-orders nhỏ hơn
4. ✅ Tăng `time_limit` và nới lỏng hao hụt tạm thời

---

### Decision Tree Nhanh

```
Số loại đoạn > 15?
├─ NO  → max_surplus = 30, stock_length = 6000mm
└─ YES → Số loại > 20?
         ├─ NO  → max_surplus = 50, stock_length theo công thức
         └─ YES → CHIA ORDER (Plan B hoặc C)
                  + max_surplus = 50/order
```

---

### Liên Hệ Hỗ Trợ

Nếu cần hỗ trợ, liên hệ:
- **Team Kỹ Thuật**: [email/Slack channel]
- **Documentation**: [`/docs/TaiLieu_ERP_CatSat/`](file:///home/trand/frappe-bench-v16/docs/TaiLieu_ERP_CatSat/)
- **Source Code**: [`apps/iea/iea/cat_laser_roi/`](file:///home/trand/frappe-bench-v16/apps/iea/iea/cat_laser_roi/)

---

**Cập nhật lần cuối**: 2026-01-26  
**Version**: 1.0  
**Tác giả**: IEA Development Team
