# Giải pháp tối ưu hóa cắt sắt với nhiều chiều dài thanh sắt nguyên bản (Multi-Stock Length)

Tài liệu này trình bày thiết kế và hướng dẫn triển khai tính năng cho phép người dùng nhập vào nhiều kích thước thanh sắt nguyên bản (ví dụ: `6000mm, 8000mm`), thuật toán tối ưu sẽ tự động đề xuất phương án phối hợp sử dụng các chiều dài này để đạt mức hao hụt thấp nhất.

---

## 1. Kiến trúc hiện tại vs Kiến trúc đề xuất

### Hiện tại (Single Stock Length)
* **Giao diện:** Chỉ cho nhập 1 số làm chiều dài cây sắt nguyên bản ($L$).
* **Giai đoạn 1 (Pattern Generation):** Sinh các patterns hợp lệ dựa trên duy nhất chiều dài $L$.
* **Giai đoạn 2 (Distribution):** Tối ưu hóa số bó/cây cho các patterns đã sinh của chiều dài $L$ đó.

### Đề xuất mới (Multi-Stock Length)
* **Giao diện:** Cho phép nhập danh sách chiều dài cách nhau bởi dấu phẩy hoặc khoảng trắng (Ví dụ: `6000, 8000`).
* **Giai đoạn 1 (Pattern Generation):** Duyệt qua từng chiều dài $L_k$ trong danh sách:
  * Sinh ra tập hợp các patterns khả thi riêng cho từng $L_k$.
  * Gán nhãn mỗi pattern thuộc về chiều dài cây sắt nguyên bản nào để phân biệt.
* **Giai đoạn 2 (Distribution):** Gom tất cả các patterns của các chiều dài lại thành một ma trận tổng hợp:
  * Thuật toán CP-SAT sẽ tự động quyết định số lượng cây cần dùng cho mỗi pattern (tương ứng với từng loại chiều dài cây nguyên bản).
  * Hàm mục tiêu vẫn là: **Tối thiểu hóa tổng hao hụt (phế liệu)**. Lúc này hao hụt của pattern $j$ thuộc cây nguyên bản $L_k$ sẽ được tính theo công thức:
    $$\text{Hao hụt}_j = L_k - \text{Tổng chiều dài các đoạn thành phẩm trong pattern } j$$

---

## 2. Chi tiết các bước triển khai code

### Bước 2.1: Cập nhật Form và Giao diện (Frontend)
Thay đổi trường nhập liệu trong [forms.py](file:///d:/cat_sat_iea/cat_sat/forms.py) từ chọn 1 số thành cho phép nhập chuỗi chứa nhiều số:

```python
# Sửa đổi trong cat_sat/forms.py
length = forms.CharField(
    label="Chiều dài thanh sắt nguyên bản (mm)",
    initial="5850 6000",
    widget=forms.TextInput(attrs={
        'class': 'form-control',
        'placeholder': 'Ví dụ: 6000, 8000'
    }),
    help_text="Nhập các chiều dài cách nhau bởi dấu phẩy hoặc khoảng trắng"
)
```

### Bước 2.2: Cập nhật API xử lý yêu cầu (Views)
Cập nhật [views.py](file:///d:/cat_sat_iea/cat_sat/views.py) để tách chuỗi chiều dài thành một danh sách các số thực:

```python
# Sửa đổi trong cat_sat/views.py
lengths_str = data.get('length', "5850")
# Tách chuỗi thành list các số thực
lengths = [float(l) for l in lengths_str.replace(',', ' ').split() if l.strip().isdigit()]
if not lengths:
    lengths = [5850.0]
```

### Bước 2.3: Nâng cấp Thuật toán Tối ưu hóa (Optimization Logic)
Chỉnh sửa [optimization_logic.py](file:///d:/cat_sat_iea/cat_sat/optimization_logic.py) để hỗ trợ danh sách `lengths`:

1. **Khởi tạo và Quản lý Cache:**
   Thay vì truyền vào 1 giá trị `length`, truyền vào danh sách `lengths`.
   * Giai đoạn 1 chạy sinh patterns lần lượt cho từng `length` trong danh sách:
     ```python
     all_solutions = [] # Chứa tuple: (hao_hut, pattern_array, stock_length)
     for L in self.lengths:
         # Sinh patterns cho chiều dài L
         patterns_for_L = self._solve_single_bar_batch_for_length(L)
         for obj, sol in patterns_for_L:
             all_solutions.append((obj, sol, L))
     ```
   * Cache key sẽ hash toàn bộ danh sách `lengths` để đảm bảo tính chính xác.

2. **Cập nhật Giai đoạn 2 (Lập mô hình CP-SAT):**
   * Tính toán ma trận hao hụt $L_j$ động cho mỗi pattern $j$ dựa trên chiều dài nguyên bản tương ứng của nó:
     $$L_j = \text{stock\_length}_j - \text{tổng\_chiều\_dài\_đoạn\_cắt}$$
   * Bộ giải CP-SAT sẽ tự động tìm phân bổ tối ưu số lượng cây cho từng loại chiều dài để đạt tổng hao hụt nhỏ nhất.

---

## 3. Lợi ích của giải pháp này
* **Tự động lựa chọn tối ưu:** Người dùng không cần chạy đi chạy lại nhiều lần để tự so sánh thủ công.
* **Tiết kiệm chi phí thực tế:** Thuật toán có thể đề xuất kết hợp thông minh (ví dụ: dùng 10 cây 6m và 5 cây 8m sẽ tối ưu hơn là chỉ dùng toàn bộ cây 6m hoặc toàn bộ cây 8m).

---

## 4. Bản hiện thực thực tế: màn "Đề xuất thanh sắt" (`cat_sat/de_xuat_*`)

Ý tưởng multi-stock-length ở trên **đã được hiện thực độc lập** trong module **Đề xuất thanh sắt** (KHÔNG đụng logic MCTĐ/MC Laser). Điểm khác so với thiết kế mục 1–2:

* Đầu vào là **định mức sản phẩm (BOM) + số bộ**, không phải danh sách đoạn cắt trực tiếp → hệ thống tự **bung định mức** ra nhu cầu số đoạn (Tầng 1).
* Với **mỗi loại sắt** (gom theo quy cách/tiết diện), ngoài việc phối hợp các chiều dài **chuẩn** người dùng nhập, còn có chế độ **vét cạn** một dải `[min_len, max_len]` để tìm chiều dài "đặt riêng" tối ưu khi không chiều dài chuẩn nào đạt ngưỡng %.
* Hao hụt tính **giống MC Laser** (khúc thừa/cây = chiều dài cây − đoạn − lưỡi cắt; đoạn dư = tồn kho, KHÔNG vào %). Xem giải thích + ví dụ số đầy đủ 500 bộ J55 ở [`PHAN_TICH_HE_THONG.md`](../PHAN_TICH_HE_THONG.md) **Phần II**.

Nguồn: [`cat_sat/de_xuat_views.py`](../cat_sat/de_xuat_views.py), [`cat_sat/de_xuat_logic.py`](../cat_sat/de_xuat_logic.py), routes trong [`cat_sat/urls.py`](../cat_sat/urls.py).

### 4.1. Các endpoint

| Endpoint | Method | Vai trò |
|---|---|---|
| `/cat_sat/de_xuat/` | GET | Render màn hình (SSR, có danh mục sản phẩm mock để demo) |
| `/cat_sat/de_xuat/materials/` | POST | **Bước 1** — bung định mức → danh sách các loại sắt (gom theo quy cách) |
| `/cat_sat/de_xuat/optimize_material/` | POST | **Bước 2** — tính đề xuất cho **MỘT** loại sắt (FE gọi lần lượt từng loại) |

> Thiết kế 2 bước (materials → optimize từng loại) giúp FE hiển thị **tiến độ dần** (mỗi loại xong hiện ngay), tránh 1 request nặng chờ lâu. Tất cả đều `@login_required`, body là JSON.

### 4.2. Input — các fields truyền lên

**Bước 1 — `POST /cat_sat/de_xuat/materials/`**

```jsonc
{
  "num_sets": 500,                 // int ≥ 1, số bộ sản xuất
  // bom: mảng hàng định mức, mỗi hàng 6 cột theo đúng thứ tự:
  // [Tên mảnh, SL/bộ, Nguyên liệu, Quy cách, Dài cắt(mm), SL/mảnh]
  "bom": [
    ["chân bàn", 4, "sắt vuông", "50*50", 660, 1],
    ["đoạn dài", 2, "sắt hộp",   "25*50", 930, 1]
  ]
}
```

Quy tắc lọc hàng (`_parse_bom`): bỏ hàng < 6 cột, hoặc `Dài cắt`/`Nguyên liệu` rỗng. Nhu cầu 1 cỡ = `SL/bộ × SL/mảnh × num_sets`. Gom theo khóa `"Nguyên liệu Quy cách"`.

**Bước 2 — `POST /cat_sat/de_xuat/optimize_material/`**

| Field | Kiểu | Mặc định | Ý nghĩa |
|---|---|---|---|
| `material` | string | "" | Tên loại sắt (chỉ để hiển thị lại) |
| `sizes` | int[] | — | Các cỡ đoạn của loại này (lấy từ output Bước 1) |
| `demands` | int[] | — | Nhu cầu tương ứng từng cỡ (cùng độ dài với `sizes`) |
| `stock_lengths` | string | — | Các chiều dài chuẩn, cách nhau space/phẩy. VD `"5850 6000"` |
| `num_sets` | int | 1 | Số bộ (đi kèm để tham chiếu) |
| `trim` | int | 0 | Tề đầu sắt (mm) |
| `max_waste_pct` | float | 1.0 | Ngưỡng hao hụt tối đa mỗi loại (%) |
| `max_surplus` | int | 10 | Cho phép **dư** tối đa mỗi cỡ (đoạn); KHÔNG cho thiếu |
| `min_len` | int | 4000 | Cận dưới dải vét cạn (mm) |
| `max_len` | int | 12000 | Cận trên dải vét cạn (mm) |
| `step` | int | 50 | Bước dò khi vét cạn (mm) |
| `time_limit_minutes` | number | 2 | Thời gian tối đa/lần giải → `×60` = giây |

> **Lưu ý:** lưỡi cắt (kerf) **không có field** — hardcode = **1mm** giống MC Laser (`de_xuat_views.py`, `_parse_params`).

Ví dụ payload Bước 2:
```jsonc
{
  "material": "sắt hộp 25*50",
  "sizes":   [930, 765, 695, 200],
  "demands": [1000, 1000, 1000, 2000],
  "stock_lengths": "5850 6000",
  "trim": 10, "max_waste_pct": 1, "max_surplus": 10,
  "min_len": 5000, "max_len": 7000, "step": 10,
  "time_limit_minutes": 2, "num_sets": 500
}
```

### 4.3. Output — cấu trúc trả về

**Bước 1 — response:**
```jsonc
{
  "status": "success",
  "num_sets": 500,
  "materials": [
    { "material": "sắt vuông 50*50", "sizes": [660],            "demands": [2000] },
    { "material": "sắt hộp 25*50",   "sizes": [930,765,695,200], "demands": [1000,1000,1000,2000] },
    { "material": "sắt vuông 20*20", "sizes": [840],            "demands": [500] }
  ]
}
```
FE lặp mảng `materials`, mỗi phần tử gọi tiếp Bước 2.

**Bước 2 — response** (`result` là dict từ `optimize_one_material`):
```jsonc
{
  "status": "success",
  "material": "sắt hộp 25*50",
  "result": {
    "feasible": true,
    "best_length": 6000,          // chiều dài đề xuất mua
    "source": "fixed",            // "fixed" = chiều dài chuẩn | "scan" = vét cạn
    "total_bars": 467,            // số cây phải mua
    "waste_pct": 0.1786,          // % hao hụt (chỉ khúc thừa; kerf & đoạn dư KHÔNG tính)
    "over_waste": false,          // true nếu waste_pct > max_waste_pct
    "max_waste_pct": 1.0,

    "cut_lengths": [930,765,695,200],   // các cỡ (thứ tự dùng chung cho produced/demands/plan.counts)
    "demands":     [1000,1000,1000,2000],
    "produced":    [1000,1000,1002,2003],  // cắt ra thực tế → Dư = produced - demands

    "total_purchased_mm": 2802000,  // tổng sắt mua = best_length × total_bars
    "total_waste_mm": 5005,         // tổng khúc thừa (phế liệu)
    "total_surplus_pieces": 5,      // tổng đoạn dư (tồn kho) = Σ(produced - demands)

    // plan: kế hoạch cắt — mỗi phần tử là 1 "kiểu cắt" và số cây dùng nó
    "plan": [
      { "stock_length": 6000, "counts": [4,1,1,4], "bars": 200, "waste_per_bar": 10 },
      { "stock_length": 6000, "counts": [1,4,2,3], "bars": 200, "waste_per_bar": 10 },
      { "stock_length": 6000, "counts": [0,0,6,9], "bars": 67,  "waste_per_bar": 15 }
    ],

    // dữ liệu để hiển thị "So sánh chiều dài" trên UI:
    "fixed_evals": [ {"length":6000,"bars":467,"waste_pct":0.1786},
                     {"length":5850,"bars":480,"waste_pct":0.297} ],
    "scan_optimal": null            // hoặc {length,bars,waste_pct} khi source="scan"
  }
}
```

Trường hợp không giải được: `result = { "feasible": false, "reason": "..." }` (vd đoạn dài hơn cây, hoặc không chiều dài nào đạt).
Lỗi request: `{ "status": "error", "message": "..." }` với HTTP 400/500.

### 4.4. Ý nghĩa các trường output khi khớp bảng trên UI

| Trường output | Cột/khối trên giao diện |
|---|---|
| `best_length` + `total_bars` | Bảng "Đề xuất mua": Chiều dài mua × Số cây |
| `waste_pct` (+ `over_waste`) | Cột "Hao hụt" (đỏ nếu vượt ngưỡng) |
| `cut_lengths` / `demands` / `produced` | Bảng "Cỡ đoạn — Cần — Cắt ra — Dư" (Dư = produced − demands) |
| `plan[].counts` / `bars` / `waste_per_bar` | Bảng "Kế hoạch cắt" (ô 0 hiện trống; HH/cây = waste_per_bar) |
| `total_purchased_mm` / `total_waste_mm` | Dòng tổng "Tổng sắt mua / Tổng khúc thừa" |
| `total_surplus_pieces` | "Đoạn dư (tồn kho)" — tách riêng, không vào % |
| `fixed_evals` / `scan_optimal` | Khối "So sánh chiều dài" |

> Toàn bộ số hao hụt ở output đã theo công thức **loại lưỡi cắt** (đồng bộ MC Laser). Công thức & ví dụ số kiểm chứng: [`PHAN_TICH_HE_THONG.md`](../PHAN_TICH_HE_THONG.md) Phần II.
