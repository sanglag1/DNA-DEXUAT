# Tài liệu tích hợp API — cat_sat_iea như một Solver Service

> **Mục đích:** Mô tả cách một hệ thống khác (FE Next.js + BE riêng của bạn) gọi tới `cat_sat_iea` để **tính toán phương án cắt sắt tối ưu**, rồi tự lưu kết quả bên BE của mình. `cat_sat_iea` đóng vai trò **solver thuần (stateless compute service)** — chỉ nhận input, trả kết quả, không lưu dữ liệu nghiệp vụ.
>
> **Trạng thái hiện tại:** Tài liệu này mô tả **API đích (target)** cần có. Một phần contract dưới đây **chưa tồn tại trong code hiện tại** và cần được xây thêm — xem [Mục 7: Khoảng cách với code hiện tại](#7-khoảng-cách-giữa-tài-liệu-này-và-code-hiện-tại). Ghi ngày: 2026-07-06.

---

## 1. Mô hình tổng thể

```
┌──────────────┐      ┌──────────────────────┐      ┌──────────────────────────┐
│  FE Next.js  │─────▶│  BE của bạn          │─────▶│ cat_sat_iea (SOLVER)     │
│  (UI nhập    │      │  • Lưu DB kết quả    │      │ • CHỈ tính, KHÔNG lưu    │
│   liệu +     │◀─────│  • Auth người dùng   │◀─────│ • Nhận JSON → trả JSON   │
│   hiển thị)  │      │  • Nghiệp vụ         │      │ • Có thể cache pattern   │
└──────────────┘      └──────────────────────┘      └──────────────────────────┘
                              │
                              ▼
                      DB của bạn (nguồn dữ liệu duy nhất)
```

**Nguyên tắc:**
- **BE gọi solver (server-to-server), KHÔNG để FE gọi thẳng** — để giấu API key và kiểm soát input.
- `cat_sat_iea` **không lưu** đơn hàng/kết quả của bạn. Mọi dữ liệu nghiệp vụ nằm ở DB của BE.
- `cat_sat_iea` **được phép giữ cache pattern** (file pickle) để tăng tốc — đây là bộ nhớ đệm kỹ thuật, không phải dữ liệu người dùng, không cần đồng bộ/backup.

---

## 2. Hai loại máy cắt (2 nhóm endpoint)

| Loại máy | Module | Đặc điểm | Dùng khi |
|---|---|---|---|
| **Máy cắt tự động (MCTĐ)** | `cat_sat` | Cắt theo **bó** nhiều cây; có "cắt tay" | Xưởng dùng máy cắt bó |
| **Máy cắt Laser** | `cat_laser_roi` | Cắt **từng cây**; có dò chiều dài tối ưu, cắt kết hợp | Xưởng dùng máy laser |

> Module `cat_laser` (bản laser cũ) không khuyến nghị dùng cho tích hợp mới — đã bị `cat_laser_roi` thay thế.

---

## 3. Xác thực

Vì BE gọi server-to-server (không dùng session/cookie), dùng **API key** qua header:

```
Authorization: Bearer <API_KEY>
Content-Type: application/json
```

> API key do `cat_sat_iea` cấp và cấu hình qua biến môi trường. Không public key này ra FE.

---

## 4. API Contract

### 4.1. Máy cắt tự động (MCTĐ)

**`POST /api/v1/cat_sat/optimize`**

Request:
```jsonc
{
  "length": 5850,                 // int, chiều dài cây sắt (mm) — bắt buộc
  "trim_start": 0,                 // int, tề đầu sắt bỏ đi (mm)
  "blade_width": 2.5,              // float, độ dày lưỡi cắt/kerf (mm)
  "factors": [14, 16, 18, 20],     // int[], các cỡ bó (cây/bó) máy hỗ trợ; [] hoặc [1] = không bó
  "no_bundle_constraint": false,   // bool, true = tính theo từng cây, bỏ ràng buộc bó
  "max_manual_cuts": 5,            // int, số cây cắt tay tối đa
  "max_surplus": 20,               // int, dung sai tồn kho ± mỗi loại đoạn
  "max_waste_percentage": 1.0,     // float, % hao hụt tối đa mỗi cây (lọc pattern)
  "time_limit_seconds": 120,       // int, giới hạn thời gian giải (KHÔNG phải thời gian cắt)
  "pieces": [                       // đơn hàng cần cắt
    { "name": "I1", "size": 2360.8, "demand": 600 },
    { "name": "I2", "size": 1160.0, "demand": 1200 }
  ]
}
```

Response 200:
```jsonc
{
  "status": "success",
  "input_echo": { /* lặp lại tham số đã dùng, để BE lưu kèm */ },
  "result": {
    "total_bars": 512,                 // tổng số cây sắt cần dùng
    "total_waste_mm": 245300.0,        // tổng hao hụt (mm)
    "total_waste_m": 245.3,            // tổng hao hụt (m)
    "waste_percentage": 0.87,          // % hao hụt
    "total_manual_cuts": 3,            // số cây cắt tay (MCTĐ)
    "total_machine_cuts": 509,         // số cây cắt máy
    "summary": [                        // tổng kết theo từng loại đoạn
      { "name": "I1", "size": 2360.8, "demand": 600,  "produced": 600,  "surplus": 0  },
      { "name": "I2", "size": 1160.0, "demand": 1200, "produced": 1202, "surplus": 2  }
    ],
    "cutting_plan": [                   // kế hoạch cắt chi tiết theo từng pattern
      {
        "pattern_index": 1,
        "waste_mm": 111.0,             // hao hụt mỗi cây theo kiểu cắt này
        "pieces": { "I1": 2, "I2": 1 },// mỗi cây cắt được gì
        "bars": 150,                   // số cây làm theo kiểu này
        "bundles": { "14": 10, "16": 0, "18": 0, "20": 0 } // (chỉ khi có bó) phân rã theo cỡ bó
      }
    ]
  }
}
```

### 4.2. Máy cắt Laser

**`POST /api/v1/cat_laser_roi/optimize`**

Request:
```jsonc
{
  "stock_length": 6000,            // int, chiều dài cây sắt (mm) — bắt buộc trừ khi bật dò tối ưu
  "trim_start": 10,                // int, tề đầu sắt (mm)
  "blade_width": 1.0,              // float, kerf (mm)
  "max_surplus": 10,               // int, dung sai tồn kho ± mỗi loại
  "max_total_surplus": 1000,       // int|null, tổng tồn kho tối đa mọi loại (dùng khi dò chiều dài)
  "max_waste_percentage": 1.0,     // float, % hao hụt tối đa mỗi cây
  "pattern_limit": 100000,         // int, giới hạn số pattern (kiểm soát thời gian)
  "time_limit_seconds": 120,       // int, giới hạn cho MỖI bước tối ưu (xem ghi chú thời gian)

  // Chế độ cắt kết hợp Laser + Tự động (tùy chọn): đánh dấu đoạn cuối
  "pieces": [
    { "name": "I1", "size": 2360.8, "demand": 600,  "is_end_piece": false },
    { "name": "I3", "size": 1289.2, "demand": 1200, "is_end_piece": true  }
  ],

  // Chế độ dò chiều dài cây sắt tối ưu (tùy chọn):
  "optimize_stock_length": false,  // bool, true = CHỈ dò chiều dài, trả về gợi ý (xem response 4.3)
  "optimize_min_length": 5000,
  "optimize_max_length": 6000,
  "optimize_search_step": 10,
  "optimize_stop_on_first": false
}
```

Response 200 (chế độ thường, `optimize_stock_length=false`): **giống cấu trúc `result` của MCTĐ** ở mục 4.1 nhưng không có `bundles`/`manual_cuts` (laser cắt từng cây):
```jsonc
{
  "status": "success",
  "input_echo": { ... },
  "result": {
    "total_bars": 480,
    "total_waste_mm": 210000.0,
    "waste_percentage": 0.73,
    "total_surplus": 8,                // tổng |thừa/thiếu| toàn bộ loại
    "summary": [ { "name": ..., "size": ..., "demand": ..., "produced": ..., "surplus": ... } ],
    "cutting_plan": [
      { "pattern_index": 1, "waste_mm": 12.4, "pieces": { "I1": 2, "I3": 1 }, "bars": 150 }
    ]
  }
}
```

### 4.3. Response chế độ dò chiều dài tối ưu (`optimize_stock_length=true`)

```jsonc
{
  "status": "success",
  "result": {
    "optimal_length": 5840,            // chiều dài cây sắt tối ưu tìm được (mm)
    "optimal_waste_percentage": 0.61,
    "optimal_total_bars": 470,
    "optimal_total_surplus": 5,
    "tests_done": 101,                 // số chiều dài đã thử
    "top_candidates": [                // top các chiều dài tốt nhất
      { "length": 5840, "bars": 470, "waste_percentage": 0.61, "total_surplus": 5 },
      { "length": 5850, "bars": 472, "waste_percentage": 0.64, "total_surplus": 6 }
    ]
  }
}
```
> Lưu ý: chế độ này **chỉ trả gợi ý chiều dài**, KHÔNG trả kế hoạch cắt chi tiết. Sau khi có `optimal_length`, gọi lại endpoint ở chế độ thường với `stock_length = optimal_length` để lấy kế hoạch cắt đầy đủ.

### 4.4. Response lỗi (chung)

```jsonc
{ "status": "error", "code": "NO_FEASIBLE_SOLUTION", "message": "Không tìm được nghiệm. Hãy tăng dung sai tồn kho / thời gian / % hao hụt." }
```
| HTTP | code | Ý nghĩa |
|---|---|---|
| 400 | `INVALID_INPUT` | Thiếu field bắt buộc / sai kiểu dữ liệu |
| 401 | `UNAUTHORIZED` | Sai/thiếu API key |
| 422 | `NO_FEASIBLE_SOLUTION` | Solver chạy nhưng không có nghiệm thỏa ràng buộc |
| 500 | `SOLVER_ERROR` | Lỗi nội bộ solver |

---

## 5. Đồng bộ vs Bất đồng bộ (QUAN TRỌNG)

Solver có thể chạy **vài giây đến vài giờ** (chế độ dò chiều dài rất lâu). BE **không nên** gọi đồng bộ rồi chờ với bài toán nặng.

### Kiểu A — Đồng bộ (cho bài toán nhỏ, `time_limit_seconds` ngắn ≤ 60–120s)
```
BE → POST /api/v1/.../optimize   (giữ kết nối chờ)
   ← 200 { result }              → BE lưu DB
```
Đơn giản, hợp cho MCTĐ / laser thường với input vừa phải.

### Kiểu B — Bất đồng bộ (khuyến nghị cho bài toán nặng / dò chiều dài)
```
1. BE → POST /api/v1/.../optimize        ← 202 { "job_id": "abc123", "status": "queued" }
2. cat_sat_iea xử lý nền (task queue)
3. BE → GET  /api/v1/jobs/abc123          ← { "status": "running", "progress": 0.45 }
                                          ← { "status": "done", "result": { ... } }
   (hoặc cat_sat_iea gọi webhook về BE khi xong: POST <callback_url> { job_id, result })
4. BE lưu result vào DB
```

**Tiến trình real-time cho FE (tùy chọn):** nếu muốn hiển thị thanh tiến trình khi đang giải, FE có thể kết nối WebSocket `ws://<cat_sat_iea>/ws/<app_name>/log/` để nhận log; còn **kết quả cuối cùng** thì luôn đi đường JSON (mục 4) để BE lưu. Hai kênh tách biệt: WS = xem tiến trình, HTTP JSON = lấy kết quả chính thức.

---

## 6. BE nên lưu gì vào DB của mình

Vì `cat_sat_iea` không lưu, BE nên lưu tối thiểu:

| Nhóm | Trường gợi ý |
|---|---|
| **Input** | Toàn bộ request đã gửi (`input_echo`) — để tái tạo/audit |
| **Metadata** | user_id, machine_type (`cat_sat`/`cat_laser_roi`), created_at, duration |
| **Kết quả tổng hợp** | total_bars, waste_percentage, total_surplus |
| **Chi tiết** | `summary` (bảng tồn kho) + `cutting_plan` (kế hoạch cắt) — lưu JSON |
| **Trạng thái** | success / error / timeout, error_message |

> Đây chính là dữ liệu mà hiện `cat_sat_iea` đang lưu ở bảng `OptimizationLog` — bạn "nhấc" nó sang BE của mình để làm chủ dữ liệu.

---

## 7. Khoảng cách giữa tài liệu này và code hiện tại

Tài liệu mô tả API **đích**. Hiện code `cat_sat_iea` **chưa** có sẵn contract này. Cần xây thêm (không phá logic solver):

| Việc cần làm trên cat_sat_iea | Mức độ | Ghi chú |
|---|---|---|
| **Trả kết quả qua HTTP JSON** thay vì WebSocket HTML | ⭐ Bắt buộc | `cat_laser_roi` hiện chỉ trả `{"status":"success"}`, số liệu nằm trong HTML bắn qua WS. Nhưng `solve_phase2()` **đã có sẵn `result` dict** (`total_bars`, `waste_percentage`, `total_surplus`, `production_plan`, `summary_df`) — chỉ cần serialize ra JSON |
| **Chuẩn hóa input** (dạng `pieces: [{name,size,demand}]` thay vì mảng 2 chiều Handsontable) | ⭐ Bắt buộc | Code hiện nhận `pieces_data` là mảng `[[name,size,demand],...]`. Nên bọc 1 lớp API convert sang định dạng sạch |
| **Token auth + bỏ `@login_required`/CSRF cho endpoint API** | ⭐ Bắt buộc | Hiện dùng session Django |
| **CORS** (nếu có lúc FE gọi thẳng) | Tùy | Không cần nếu chỉ BE↔solver |
| **Cơ chế job bất đồng bộ + `job_id`** | Nên có | Cho bài toán nặng; hiện chưa có, đang chạy đồng bộ trong request |
| **Tắt ghi `OptimizationLog` / Redis** (để stateless) | Nên có | Giữ `patterns_cache` để tăng tốc |

**Cách triển khai gợi ý:** tạo một Django app mới `api/` chứa các REST endpoint ở trên, gọi lại `optimization_logic.py` (KHÔNG sửa solver), trả JSON. Như vậy bản web hiện tại vẫn chạy song song, không ảnh hưởng.

---

## 8. Ghi chú về đơn vị & hành vi (tránh hiểu nhầm)

- Mọi kích thước tính bằng **mm**.
- `time_limit_seconds` là **thời gian cho phép máy tính GIẢI bài toán**, KHÔNG phải thời gian máy cắt thực tế. Hệ thống **không** mô hình hóa tốc độ cắt / năng suất / sản lượng theo giờ.
- Với `cat_laser_roi` chế độ thường, tổng thời gian thực tế có thể tới **~3× `time_limit_seconds`** vì solver chạy 3 bước tối ưu tuần tự (hao hụt → tồn kho → ưu tiên).
- `waste_percentage` = tổng hao hụt ÷ (chiều dài cây × tổng số cây) × 100 — mẫu số là **tổng vật liệu đã tiêu thụ**.
- `surplus` dương = **thừa** (tồn kho), âm = **thiếu**; bị khống chế bởi `max_surplus`.
- **Không có yếu tố chi phí/tiền tệ** trong kết quả — chỉ có số cây, hao hụt, tồn kho.
