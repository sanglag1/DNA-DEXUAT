# Phân tích hệ thống Cắt Sắt IEA (cat_sat_iea)

> Tài liệu này ghi lại kết quả review toàn bộ codebase tại thời điểm 2026-07-03 (commit `0c63a1d`), phục vụ mục đích hiểu logic nghiệp vụ, kiến trúc và cách vận hành hệ thống.

## 1. Tổng quan

Đây là hệ thống nội bộ giải **bài toán cắt vật liệu tối ưu (Cutting Stock Problem – 1D)**: từ các cây sắt/thép nguyên có chiều dài chuẩn, tính ra **phương án cắt** thành các đoạn theo đơn hàng sao cho **tốn ít cây sắt nhất / hao hụt (phế liệu) ít nhất**.

- **Framework**: Django 5.1 (đồng bộ) + Django Channels (bất đồng bộ qua WebSocket) chạy trên **Daphne** (ASGI server).
- **Bộ giải tối ưu (solver)**: [Google OR-Tools CP-SAT](https://developers.google.com/optimization) (`ortools.sat.python.cp_model`) là chính; `gurobipy` có khai báo trong `requirements.txt` nhưng qua review code hiện tại các module đều dùng CP-SAT (Gurobi có thể là công cụ dự phòng/thử nghiệm trước đây).
- **Hạ tầng**: PostgreSQL (dữ liệu), Redis (cache pattern + channel layer cho WebSocket), Caddy (reverse proxy/HTTPS), Docker Compose (triển khai production) — xem `docker-compose.prod.yml`, `Dockerfile`, `Caddyfile`.
- **Xuất dữ liệu**: Excel (`openpyxl`) cho kết quả pattern.
- **Xác thực**: Django auth (session) + **OTP 2 bước (TOTP qua `pyotp`)**, admin có thể xem trực tiếp mã OTP hiện tại của user.

### Điều hướng cấp cao (`iea_project/urls.py`)

```
/                       -> redirect vào cat_laser_roi:index (trang mặc định)
/accounts/              -> đăng nhập / OTP / đăng xuất
/cat_sat/               -> module "Cắt sắt" (tự động + cắt tay, OR-Tools)
/cat_laser/             -> module "Cắt Laser" (máy cắt laser MCTĐ)
/cat_laser_roi/         -> module "Cắt Laser ROI" (bản đầy đủ tính năng nhất)
/logs/                  -> optimization_logs — lịch sử các lần chạy tối ưu
/admin/                 -> Django admin
```

Có 3 module nghiệp vụ **độc lập** (mỗi module có `models.py`, `forms.py`, `views.py`, `optimization_logic.py`, `templates/` riêng) cùng giải chung một dạng bài toán nhưng theo 3 kịch bản khác nhau.

---

## 2. Nguyên lý thuật toán chung (Cutting Stock 2 giai đoạn)

Cả 3 module đều dùng chung một chiến lược **2 giai đoạn (2-phase)**, mô hình hoá bằng CP-SAT:

### Giai đoạn 1 — Sinh Pattern (Pattern Generation)

Với 1 cây sắt nguyên có chiều dài `L`, cần tìm tất cả **cách cắt khả thi** (pattern) — tức các bộ số nguyên `x = (x_1, x_2, ..., x_n)` (số lượng mỗi loại đoạn cắt trong 1 cây) sao cho:

```
tổng_vật_liệu_dùng = Σ(x_i * kích_thước_đoạn_i) + (Σx_i) * độ_rộng_lưỡi_cắt (kerf)
tổng_vật_liệu_dùng  ≤  L − tề_đầu_sắt (trim_start)
tổng_vật_liệu_dùng  ≥  L * (1 − %hao_hụt_tối_đa_cho_phép)
```

- **Tề đầu sắt (trim_start / te_dau_sat)**: đoạn đầu cây sắt luôn bị cắt bỏ (không dùng được), cấu hình được (mặc định 10mm).
- **Độ rộng lưỡi cắt (blade width / kerf)**: mỗi nhát cắt "ăn" mất một khoảng vật liệu, phải cộng dồn theo số nhát cắt.
- Bài toán này được giải bằng CP-SAT ở chế độ **liệt kê toàn bộ nghiệm thoả mãn** (`enumerate_all_solutions = True`) qua `SolutionCallback` — không phải bài toán tối ưu mà là bài toán **thoả mãn ràng buộc (CSP)**, thu thập tất cả pattern có hao hụt nằm trong ngưỡng cho phép, giới hạn số lượng bằng `pattern_limit`/`SOLUTION_LIMIT` để tránh bùng nổ tổ hợp.
- Toàn bộ số liệu được **scale lên số nguyên** (nhân 10 hoặc 100) trước khi đưa vào CP-SAT vì solver làm việc tốt nhất với số nguyên.
- Kết quả GĐ1 được **cache vào file pickle** (qua `utils/cache_utils.py::PatternCache`) theo cache-key = hash(MD5/SHA256) của các tham số đầu vào (chiều dài, danh sách đoạn, lưỡi cắt, tề đầu, %hao hụt...). Nhờ vậy nếu chạy lại với tham số y hệt, hệ thống load thẳng từ cache thay vì giải lại từ đầu (rất tốn thời gian nếu enumerate toàn bộ nghiệm).

### Giai đoạn 2 — Phân bổ số lượng cây sắt theo Pattern (Distribution/Assignment)

Từ tập pattern ở GĐ1 (dạng ma trận A: hàng = loại đoạn, cột = pattern), bài toán tối ưu chọn **số lần dùng mỗi pattern** (biến nguyên `x_j` hoặc `b[j][r]`) sao cho:

- Tổng số đoạn được cắt ra của mỗi loại nằm trong khoảng `[nhu_cầu − dung_sai, nhu_cầu + dung_sai]` (cho phép **cả thừa lẫn thiếu**, dung sai = `max_surplus`/`max_stock_over`).
- **Mục tiêu tối ưu đa cấp (lexicographic / hierarchical optimization)**, giải tuần tự nhiều bước, mỗi bước cố định kết quả bước trước làm ràng buộc cho bước sau:
  1. **Ưu tiên 1**: tối thiểu hoá **tổng hao hụt vật liệu**.
  2. **Ưu tiên 2**: trong số các nghiệm có hao hụt bằng mức tối thiểu, tối thiểu hoá **tổng độ lệch tồn kho** (Σ|thừa/thiếu|).
  3. **Ưu tiên 3 (tuỳ chọn)**: tối ưu theo **độ ưu tiên pattern** (ví dụ ưu tiên pattern có đoạn cuối "khoét lỗ" ít nhất).
- Kỹ thuật: dùng `model.Add(... == best_value)` để khoá giá trị mục tiêu vừa tìm được trước khi chuyển sang mục tiêu phụ tiếp theo — đây là kỹ thuật **tối ưu đa mục tiêu theo thứ tự ưu tiên (weighted/lexicographic goal programming)**.

---

## 3. Chi tiết từng module

### 3.1. `cat_sat` — Cắt sắt Tự động / Thủ công

File chính: [`cat_sat/optimization_logic.py`](cat_sat/optimization_logic.py) (801 dòng), [`cat_sat/column_generator.py`](cat_sat/column_generator.py), [`cat_sat/views.py`](cat_sat/views.py).

**Input người dùng nhập** (bảng Handsontable trên UI):
- Tên đoạn, kích thước, số lượng cần (nhiều dòng).
- Chiều dài cây sắt (`length`), tề đầu sắt (`te_dau_sat`), độ rộng lưỡi cưa (`blade_width`).
- `hao_hut_percent`: % hao hụt tối đa cho phép mỗi cây.
- `max_manual_cuts`: số lần cắt tay tối đa cho phép.
- `max_stock_over`: dung sai tồn kho (thừa/thiếu) mỗi loại đoạn.
- `factors`: **hệ số bó sắt** (cây/bó) — ví dụ factor 3 nghĩa là 1 "bó" gồm 3 cây được cắt cùng lúc (dùng cho máy cắt bó nhiều cây một lần); factor 1 = cắt tay từng cây.
- `no_bundle_constraint`: tắt/bật ràng buộc bó sắt.

**Đặc điểm riêng của module này**:
- Lớp `SteelCuttingOptimizer` gói toàn bộ pipeline: cache → sinh pattern (GĐ1, class `SolutionAndLogCollector` kế thừa `CpSolverSolutionCallback`) → phân bổ (GĐ2).
- Sau khi GĐ1 cho ra pattern, có bước lọc: nếu số loại đoạn > 5, chỉ giữ pattern có **≤ 5 loại đoạn khác 0** trong 1 cây (giới hạn kỹ thuật vì máy cắt tự động MCTĐ chỉ nhận tối đa 5 input).
- GĐ2 có 2 biến thể:
  1. **Có ràng buộc bó sắt** (`optimize_distribution`): biến quyết định `b[j][r]` = số bó pattern j dùng hệ số bó `fr`; tổng số cây = `Σ fr * b[j][r]`. Có ràng buộc riêng cho **số lần cắt tay tối đa** (factor = 1).
  2. **Không ràng buộc bó** (`_optimize_distribution_no_bundle`): đơn giản hơn, biến `x[j]` = số cây dùng trực tiếp cho pattern j (không nhân theo bó) — giống cách làm của `cat_laser_roi`.
- Hàm mục tiêu GĐ2: `Minimize(Loss * W1 + Bundles/Bars * W2)` với `W1 = 10^6 ≫ W2 = 1` để đảm bảo **hao hụt luôn được ưu tiên tuyệt đối**, số bó/cây chỉ là tiêu chí phụ (tie-break) khi hao hụt bằng nhau.
- Kết quả xuất ra **HTML bảng** (qua `pandas.Styler`) để hiển thị trực tiếp lên giao diện qua WebSocket, gồm: bảng tổng kết (tồn kho highlight đỏ nếu thiếu/xanh nếu thừa) và bảng kế hoạch cắt chi tiết theo từng pattern.
- Có endpoint **xuất Excel kết quả GĐ1** (`export_excel_phase1`) với 2 sheet: danh sách pattern và nhu cầu cắt.
- Model DB duy nhất: `Solution` (length, segment_sizes, blade_width, obj_value, solution) — có vẻ là bảng lưu nghiệm cũ, tuy hiện tại pipeline chính dùng cache file pickle chứ không phải bảng này trực tiếp.

### 3.2. `cat_laser` — Cắt Laser (MCTĐ)

File chính: [`cat_laser/optimization_logic.py`](cat_laser/optimization_logic.py) (295 dòng), [`cat_laser/views.py`](cat_laser/views.py), [`cat_laser/utils.py`](cat_laser/utils.py).

- Chiều dài cây sắt chọn theo danh sách cố định: **5740 / 5850 / 6000 mm**.
- Độ rộng lưỡi cắt phân biệt: một giá trị cho MCTĐ (2.5 hoặc 3.0mm — chọn qua form) áp dụng cho **đoạn có kích thước nguyên**, và có `do_day_luoi_cua()` (trong `utils.py`) tính hệ số lưỡi mài (`k_factors`) riêng cho từng đoạn dựa trên kích thước.
- Sinh pattern (`generate_patterns`) có xử lý đặc biệt: các vị trí "đặc biệt" (hệ số lưỡi mài `k_i != 1`) được gắn biến nhị phân `b_i`, và tuỳ theo **số lượng đoạn đặc biệt xuất hiện trong pattern (0/1/≥2)** mà áp constant khác nhau (`c = 60/0/15`) vào công thức giới hạn — đây là quy tắc nghiệp vụ đặc thù của máy laser (có thể liên quan khoảng hở an toàn giữa các lần khoét/đổi lưỡi).
- Giải phân bổ (`solve_patterns`): đơn giản hơn 2 module kia — chỉ có 1 mục tiêu `Minimize(tổng_hao_hụt)`, ràng buộc tồn kho `0 ≤ (sản_xuất − nhu_cầu) ≤ SO_LUONG_TON_KHO`.
- Module này có vẻ là **phiên bản sớm/đơn giản hơn**, ít tính năng nâng cao (không có ưu tiên đa cấp, không tối ưu chiều dài) so với `cat_laser_roi`.
- Có class `TeeStream` để redirect `stdout`/`stderr` sang WebSocket, giúp người dùng theo dõi log giải bài toán real-time.

### 3.3. `cat_laser_roi` — Module đầy đủ tính năng nhất (module mặc định của hệ thống)

File chính: [`cat_laser_roi/optimization_logic.py`](cat_laser_roi/optimization_logic.py) (835 dòng) — đây là **module được phát triển tích cực nhất**, chứa nhiều biến thể thuật toán và file test/debug riêng cho các case thực tế (`solve_CO2201_00249*.py`, `test_min_surplus.py`, `test_split_I3_I5.py`...).

**Input chính** (`cat_laser_roi/forms.py`):
- `stock_length`, `trim_start` (tề đầu, cấu hình được, mặc định 10mm — bổ sung gần đây theo git log), `max_waste_percentage`.
- `max_surplus`: dung sai **cho từng loại đoạn** (cho phép cả thừa và thiếu).
- `max_total_surplus`: **giới hạn tổng tồn kho toàn bộ các loại cộng lại** (tính năng bổ sung gần đây, chỉ áp dụng khi bật chế độ tìm chiều dài tối ưu).
- `use_priority_constraint`: ưu tiên pattern có "đoạn cuối khoét lỗ ít nhất".
- `pattern_limit`: giới hạn số pattern tối đa sinh ra (chống bùng nổ tổ hợp / kiểm soát thời gian).
- `use_combined_mode` / `is_doan_cuoi` (đánh dấu "đoạn cuối" cho từng loại): chế độ **cắt kết hợp Laser + Tự động**.
- `optimize_stock_length` + `optimize_min_length/max_length/optimize_search_step/optimize_stop_on_first`: **tự động dò tìm chiều dài cây sắt tối ưu** trong một khoảng.
- `time_limit_minutes`: giới hạn thời gian chạy solver.

**Các hàm chính trong `optimization_logic.py`:**

1. **`find_efficient_cutting_patterns` / `get_or_calculate_patterns`** (GĐ1): sinh pattern như nguyên lý chung ở mục 2, có cache riêng (thư mục `patterns_cache/`), kiểm tra nếu cache không đủ số lượng pattern yêu cầu (`limit`) thì tự động chạy lại và ghi đè cache.

2. **`solve_phase2`** (GĐ2): logic tối ưu đa cấp chi tiết nhất hệ thống:
   - Lọc pattern theo `use_priority_constraint` (chỉ giữ pattern có đoạn ≥ 60mm) và tính `Priority_Score`.
   - Lọc pattern theo **chế độ kết hợp Laser + Tự động** (`is_doan_cuoi`): với các đoạn được tick, pattern hợp lệ phải thoả 1 trong 3 điều kiện — (a) có đoạn dài (≥60mm) xuất hiện ≥1 lần, (b) có đoạn ngắn (<60mm) xuất hiện đủ số lần tối thiểu `trunc(60/kích_thước)+1`, hoặc (c) hao hụt pattern ≥ 60mm. Đây là quy tắc nghiệp vụ để tránh những pattern không khả thi khi kết hợp 2 công nghệ cắt.
   - Biến `surplus_i = sản_xuất_i − nhu_cầu_i` (có thể âm/dương), ràng buộc `-max_surplus ≤ surplus_i ≤ max_surplus`, và biến tuyệt đối `abs_surplus_i` (qua `model.AddAbsEquality`) để tối ưu.
   - Giải tuần tự 3 mục tiêu (xem mục 2): hao hụt → tổng |chênh lệch tồn kho| → độ ưu tiên (nếu bật).
   - Trả về kết quả dạng dict có cấu trúc (`total_bars`, `total_waste_mm`, `waste_percentage`, `total_surplus`, `production_plan`, `summary_df`) để dùng lại được cho các chức năng khác (khác với 2 module kia chỉ in ra HTML).

3. **`find_optimal_stock_length`**: tính năng nổi bật riêng của module này — **duyệt toàn bộ (brute-force) một khoảng chiều dài cây sắt** (`min_length` → `max_length`, bước nhảy `step`), với mỗi chiều dài chạy **đầy đủ cả GĐ1 và GĐ2**, so sánh kết quả theo thứ tự ưu tiên: `% hao hụt` (tolerance 0.01%) → `tổng tồn kho` → `tổng số cây`, để tìm chiều dài tối ưu nhất giúp giảm hao hụt/tồn kho. Có thể dừng sớm ngay khi tìm được nghiệm khả thi đầu tiên (`stop_on_first`) để tiết kiệm thời gian. Có lưu kết quả từng bước vào **Redis** (TTL 7 ngày) để theo dõi tiến trình / tra cứu lại.

**Realtime UX**: `consumers.py` + `routing.py` (WebSocket) stream log của solver (dùng `TeeStream` async ghi vào `LOG_HISTORY` + gửi qua `channel_layer.group_send`) — cho phép người dùng thấy tiến trình giải (số pattern tìm được, % hao hụt tạm thời, thời gian còn lại...) theo thời gian thực thay vì phải chờ và không biết máy có đang chạy hay treo.

### 3.4. `accounts` — Xác thực người dùng

- Model `OTPCode`: liên kết 1-1 với `User`, lưu `secret_key` (TOTP, tự sinh nếu chưa có), `is_active` (bật/tắt yêu cầu OTP cho từng user), có sẵn hàm `get_current_otp()` để **admin xem trực tiếp mã OTP hiện tại** của user (hữu ích khi hỗ trợ user bị mất thiết bị OTP).
- Luồng đăng nhập 2 bước: `login_view` xác thực user/pass trước → nếu user có `OTPCode.is_active = True` thì yêu cầu nhập thêm mã OTP (`verify_otp_view`, AJAX) mới hoàn tất đăng nhập; nếu không cần OTP thì đăng nhập thẳng.
- Toàn bộ view nghiệp vụ (`cat_sat`, `cat_laser_roi`) đều có `@login_required`.

### 3.5. `optimization_logs` — Nhật ký / Audit

Model `OptimizationLog`: `user` (FK, SET_NULL nếu xoá user), `module` (`cat_sat` hoặc `cat_laser_roi`), `created_at`, `duration_seconds`, `input_data`/`parameters`/`output_summary` (JSONField), `status` (`success`/`error`/`timeout`), `error_message`. Sắp xếp mặc định theo `-created_at`. Đây là bảng **audit log** ghi lại từng lần chạy tối ưu (ai chạy, module nào, mất bao lâu, tham số gì, kết quả tóm tắt) — phục vụ tra cứu lại lịch sử/khắc phục sự cố; không thấy `cat_laser` trong `MODULE_CHOICES` (module này có thể chưa được tích hợp ghi log).

### 3.6. Ghi chú: `cat_sat/column_generator.py`

File này (65 dòng) là một **script minh hoạ độc lập** về kỹ thuật *column generation* thực thụ (dùng `pywraplp` LP solver GLOP giải bài toán chính, SCIP giải bài toán con knapsack dựa trên **giá đối ngẫu — dual value**) với dữ liệu hard-code (`stock_length=100`, `lengths=[20,30,40]`...). Qua kiểm tra, **không thấy được import/gọi từ `views.py` hay `optimization_logic.py`** của `cat_sat` — có vẻ là code tham khảo/thử nghiệm còn sót lại, không nằm trong luồng xử lý chính (luồng chính dùng enumerate + cache như mô tả ở mục 2).

---

## 4. Hạ tầng & Vận hành

### Cache & hiệu năng
- **`utils/cache_utils.py::PatternCache`**: lớp cache thống nhất cho cả 3 module — ghi/đọc file pickle (`patterns_cache/patterns_<hash>.pkl`) kèm metadata JSON, dùng **atomic write** (ghi file tạm rồi rename) để tránh hỏng cache khi ghi giữa chừng. Cache-key = hash các tham số đầu vào → cùng tham số thì tái sử dụng kết quả GĐ1, tránh phải enumerate lại toàn bộ pattern (vốn rất tốn thời gian với solver liệt kê toàn bộ nghiệm).
- Redis dùng cho 2 việc: (1) **Channel layer** của Django Channels (truyền message WebSocket giữa các worker), (2) lưu kết quả tạm khi chạy `find_optimal_stock_length` (dò chiều dài tối ưu).

### Realtime feedback
Cả 3 module đều **redirect `stdout`** sang một `TeeStream` custom trong lúc solver chạy, để mọi `print()` trong logic tối ưu (tiến trình, log Gurobi/OR-Tools, bảng kết quả HTML...) được đẩy real-time qua WebSocket tới trình duyệt người dùng — đây là lý do UI có thể hiển thị log "đang giải..." trực tiếp thay vì chỉ có loading spinner.

### Triển khai (Production — `docker-compose.prod.yml`)
```
Caddy (reverse proxy, HTTPS, cổng 80/443)
   └── web (Django/Daphne, ASGI)
          ├── PostgreSQL (dữ liệu)
          └── Redis (cache pattern + channel layer)
```
Volume ánh xạ ra ngoài container: `./data/patterns_cache` (cache pattern bền vững qua các lần deploy) và `./data/logs` (log ứng dụng).

### Cấu hình khác đáng chú ý (`iea_project/settings.py`)
- `DAPHNE_REQUEST_TIMEOUT = 1800` (30 phút) — vì bài toán tối ưu có thể chạy lâu (đặc biệt chế độ dò chiều dài tối ưu chạy hàng chục lần GĐ1+GĐ2).
- `TIME_ZONE = 'Asia/Ho_Chi_Minh'`.
- Có thể chạy với SQLite (dev, mặc định khi không có `DB_HOST`) hoặc PostgreSQL (production, qua biến môi trường).

### CI/CD (`.github/workflows/deploy.yml`)
Mỗi lần push lên nhánh `main`, GitHub Actions tự động:
1. SSH vào server production (thông tin qua secrets `DO_HOST`/`DO_USERNAME`/`DO_SSH_KEY`/`DO_SSH_PORT`), `cd /opt/cat_sat_iea`, `git pull origin main`.
2. Rebuild & deploy lại toàn bộ stack: `docker compose -f docker-compose.prod.yml up -d --build`.
3. **Health check**: chờ 15s, liệt kê trạng thái container (`docker ps --filter name=catsat`), và `curl` thử `http://localhost:8000/accounts/login/` để xác nhận app phản hồi.

Đây là pipeline **deploy tự động không cần thao tác thủ công** mỗi khi merge code vào `main` — cần lưu ý vì bất kỳ commit nào lên `main` sẽ lập tức lên production.

---

## 5. Nhận xét tổng hợp

- **Bản chất bài toán**: 1D Cutting Stock Problem cổ điển, giải bằng chiến lược **sinh pattern trước (enumerate) rồi phân bổ số lượng sau (assignment)** — một cách tiếp cận phổ biến và hiệu quả khi số loại đoạn cắt không quá lớn, tương tự kỹ thuật "column generation" đơn giản hoá (tên file `column_generator.py` trong `cat_sat` gợi ý điều này) nhưng thực chất đang dùng brute-force enumerate + cache thay vì column generation thực sự (sinh cột theo giá đối ngẫu — dual price).
- **`cat_laser_roi` là module lõi/mặc định**, tính năng phong phú nhất và được maintain tích cực nhất (dựa trên số lượng file test/debug và lịch sử commit gần đây: hỗ trợ thừa/thiếu tồn kho, `trim_start` cấu hình được, cập nhật layout UI...).
- **`cat_sat`** bổ sung khái niệm **"bó sắt" (bundle/factor)** — đặc thù cho quy trình cắt tay theo bó nhiều cây cùng lúc, mà `cat_laser`/`cat_laser_roi` không có (2 module này cắt từng cây độc lập qua máy laser/tự động).
- **`cat_laser`** có vẻ là phiên bản cũ/đơn giản hơn, ít được cập nhật gần đây so với `cat_laser_roi`.
- Điểm mạnh về UX: streaming log real-time qua WebSocket giúp người vận hành theo dõi được tiến trình của một tác vụ tính toán có thể kéo dài vài phút đến hàng giờ (chế độ dò chiều dài tối ưu).
- Điểm cần lưu ý khi bảo trì: nhiều logic nghiệp vụ đặc thù (ngưỡng 60mm, hằng số c=60/0/15 trong `cat_laser`, quy tắc lọc pattern khi kết hợp Laser+Tự động trong `cat_laser_roi`) được hard-code trong code mà không có giải thích rõ ràng ngoài comment tiếng Việt ngắn gọn — nên cần người hiểu nghiệp vụ xưởng cắt để xác nhận khi sửa đổi.

---

# PHỤ LỤC KỸ THUẬT (dành cho việc port sang hệ thống khác, vd Next.js)

> Phần dưới đây trích **chính xác** từ source code (không diễn giải lại bằng lời) để một AI/dev khác có thể tái tạo đúng logic mà không cần đọc lại toàn bộ repo gốc. Vẫn khuyến nghị giữ quyền truy cập `optimization_logic.py` của 3 module khi cần đối chiếu sâu hơn.

## A. API Spec đầy đủ

### A.1. `cat_sat` (`/cat_sat/...`)

**`GET /cat_sat/`** → render form (không có API riêng, chỉ SSR).

**`POST /cat_sat/optimize/`** — chạy tối ưu (yêu cầu đăng nhập, session cookie).

Request JSON body:
```jsonc
{
  "length": 6000,                 // int, chiều dài cây sắt (mm)
  "te_dau_sat": 10,                // int, tề đầu sắt (mm)
  "blade_width": 3.0,              // float, độ rộng lưỡi cưa (mm)
  "max_manual_cuts": 5,            // int, số lần cắt tay tối đa
  "max_stock_over": 10,            // int, dung sai tồn kho (áp dụng ± cho mỗi loại đoạn)
  "hao_hut_percent": 1.0,          // float, % hao hụt tối đa mỗi cây (mặc định 1 nếu thiếu)
  "time_limit_minutes": 2,         // int, x3 lần cho tổng thời gian GĐ2 (xem mục B.3)
  "factors": "1,3",                // string, hệ số bó sắt cách nhau bởi dấu , hoặc . hoặc khoảng trắng; rỗng -> mặc định [1]
  "no_bundle_constraint": false,   // bool, true = GĐ2 không ràng buộc bó (theo cây)
  // pieces_data: mảng hàng từ bảng Handsontable (3 cột: Tên sắt, Kích thước, SL Cần)
  "pieces_data": [
    ["A1", 2360.8, 600],
    ["A2", 1684.8, 1200],
    ["A3", 565, 1200]
  ]
}
```
Lưu ý: hàng nào có bất kỳ ô nào null trong 3 cột đầu sẽ bị loại (`row[0] is not None and row[1] is not None and row[2] is not None`).

Response 200 (success):
```jsonc
{
  "status": "success",
  "solutions": [[obj_value, [x0, x1, x2]], ...],   // list[(float, list[int])] — mỗi pattern: hao hụt = length - obj_value
  "distribution": [[...]]  // ma trận b_opt (n patterns x số factor dương) nếu no_bundle_constraint=false,
                            // hoặc mảng 1D x_opt (n patterns) nếu no_bundle_constraint=true
}
```
Response lỗi: `{"status": "error", "message": "..."}` với status code 400 (thiếu dữ liệu) hoặc 500 (lỗi solver/exception, kèm traceback được `print()` ra WebSocket).

**`POST /cat_sat/export-excel-gd1/`** — xuất Excel danh sách pattern GĐ1 (đọc lại từ cache pickle, KHÔNG chạy lại GĐ1 nếu đã có cache khớp key `{length, segment_sizes, blade_width, te_dau_sat, hao_hut_percent}`).

Request JSON body: giống trên nhưng chỉ cần `length`, `te_dau_sat`, `blade_width`, `hao_hut_percent`, `pieces_data`.
Response: file `.xlsx` (header `Content-Disposition: attachment`), tên file `KetQua_GD1_Sat{length}mm_{YYYYMMDD_HHMM}.xlsx`. Nếu chưa có cache → 404 `{"status": "error", "message": "Chưa có dữ liệu GĐ 1. Hãy chạy tối ưu trước."}`.

### A.2. `cat_laser_roi` (`/cat_laser_roi/...`) — module mặc định (trang chủ `/` redirect vào đây)

**`POST /cat_laser_roi/run_optimization/`** (login required)

Request JSON body:
```jsonc
{
  "stock_length": 5850,                  // int/float, bắt buộc trừ khi optimize_stock_length=true
  "max_waste_percentage": 1.0,           // float, %, sẽ được chia 100 thành decimal trong code
  "max_surplus": 10,                     // int, dung sai ± mỗi loại đoạn
  "max_total_surplus": 1000,             // int|null, tổng tồn kho tối đa mọi loại cộng lại (chỉ áp dụng khi optimize_stock_length=true)
  "use_priority_constraint": false,      // bool — hiện luôn set false ở form (tính năng "priority" đã disable nghiệp vụ, priorities_list luôn = [0,...])
  "pattern_limit": 100000,               // int, số pattern tối đa GĐ1
  "optimize_stock_length": false,        // bool, bật thì CHỈ chạy dò chiều dài tối ưu, KHÔNG chạy GĐ2 chi tiết
  "optimize_min_length": 5000,
  "optimize_max_length": 6000,
  "optimize_search_step": 10,
  "optimize_stop_on_first": false,
  "trim_start": 10,                      // int, tề đầu sắt (mm)
  "time_limit_minutes": 2,               // bắt buộc, x60 = giây, x3 = tổng thời gian 3 mục tiêu lexicographic
  // pieces_data: 4 cột [Tên sắt, Kích thước, SL Cần, ĐOẠN CUỐI(checkbox bool)]
  "pieces_data": [
    ["I1", 2360.8, 600, false],
    ["I3", 1289.2, 1200, true],
    ["I5", 46, 1200, true]
  ]
}
```
Lọc hàng hợp lệ: yêu cầu `len(item) >= 3` và 3 cột đầu không null/rỗng; cột 4 (`is_doan_cuoi`) optional, mặc định `false`.

Response 200 — **CHÚ Ý: response JSON hầu như không chứa kết quả số liệu**, toàn bộ bảng kết quả (HTML `pandas.Styler`) được stream qua WebSocket, không trả trong body HTTP:
```jsonc
// chế độ bình thường:
{"status": "success", "message": "Optimization process finished."}
// chế độ optimize_stock_length=true:
{"status": "success", "message": "Optimal length search completed."}
```
→ **Đây là điểm khác biệt lớn so với `cat_sat`**: FE của `cat_laser_roi` phải tự parse bảng HTML nhận qua WebSocket để lấy số liệu (không có JSON kết quả có cấu trúc trả về qua HTTP). Nếu port sang Next.js nên đổi thiết kế: để `solve_phase2()`/`find_optimal_stock_length()` trả `result` dict (đã có sẵn cấu trúc `total_bars`, `total_waste_mm`, `waste_percentage`, `total_surplus`, `production_plan`, `summary_df` — xem mục B.2) thẳng qua JSON response thay vì chỉ in HTML.

### A.3. `cat_laser` (`/cat_laser/...`)

**`POST /cat_laser/optimize`** (không có `login_required` decorator — khác 2 module kia)

Request JSON:
```jsonc
{
  "length": 5850,
  "segment_sizes": [2360.8, 1684.8, 1289.2, 1162.2, 565, 46],
  "demands": [600, 1200, 1200, 600, 1200, 1200],
  "blade_width_mctd": 3.0,        // dùng để tính k_factors qua do_day_luoi_cua()
  "max_stock_over": 20
}
```
Response: `{"status": "success"}` — tương tự `cat_laser_roi`, không trả số liệu qua JSON, chỉ qua WebSocket (bảng text đơn giản, không phải HTML table).

### A.4. `accounts`

| Endpoint | Method | Request | Response |
|---|---|---|---|
| `/accounts/login/` | GET | – | render form login |
| `/accounts/login/` | POST | form-encoded: `username`, `password` | Nếu user có `OTPCode.is_active=True`: render lại trang kèm `show_otp_modal=True` (session lưu `pending_user_id`, `pending_username`). Nếu không: login thẳng, redirect `cat_sat:index`. Sai user/pass: render lại kèm `error_message`. |
| `/accounts/verify-otp/` (tên path cần xem `accounts/urls.py`) | POST (AJAX) | `{"otp_code": "123456"}` | `{"success": true, "redirect": "/"}` hoặc `{"success": false, "error": "..."}` |
| `/accounts/logout/` | GET/POST | – | redirect `accounts:login` |
## B. Công thức/Ràng buộc chính xác (trích code, không diễn giải)

### B.1. Sinh pattern (GĐ1) — công thức chung 3 module

Biến: `x_i` = số lượng đoạn loại i trong 1 cây (int, thường bound `[0,30]`).

```
scale = 10  (cat_sat, cat_laser_roi)   |  scale nhân trực tiếp 100 (cat_laser, xem riêng bên dưới)
seg_scaled[i]   = round(segment_size[i] * scale)
blade_scaled    = round(blade_width * scale)
length_scaled   = round(length * scale)
trim_scaled     = round(trim_start * scale)      // te_dau_sat / trim_start

total_material_scaled = Σ(seg_scaled[i] * x_i) + blade_scaled * Σx_i
usable_length          = length_scaled - trim_scaled

ràng buộc:
  total_material_scaled <= usable_length
  total_material_scaled >= round(length_scaled * (1 - max_waste_percentage))
     // cat_sat: max_waste_percentage đơn vị %, công thức: length_scaled*(1 - hao_hut_percent/100)
     // cat_laser_roi: max_waste_percentage ĐÃ Ở DẠNG DECIMAL (0.01 = 1%) khi truyền vào hàm
```

Solver: `cp_model.CpSolver()` với `enumerate_all_solutions = True`, dùng `SolutionCallback` để thu thập TẤT CẢ nghiệm thoả ràng buộc (không phải bài toán tối ưu — bài toán thoả mãn/CSP), dừng khi đạt `max_solutions`/`pattern_limit`.

`cat_sat` — lọc bổ sung sau khi có `batch` nghiệm thô:
```python
# 1. Bỏ pattern có hao hụt < tề đầu (không đủ chỗ chừa tề đầu)
batch = [(obj, sol) for obj, sol in batch if obj + te_dau_sat <= length + 1e-5]
# 2. Nếu > 5 loại đoạn: chỉ giữ pattern có <= 5 loại đoạn khác 0 (giới hạn máy MCTĐ)
if len(segment_sizes) > 5:
    batch = [(obj, sol) for obj, sol in batch if sum(1 for x in sol if x > 0) <= 5]
```

`cat_laser` — công thức GĐ1 KHÁC 2 module kia (không có trim_start, có phân loại theo số "đoạn đặc biệt" k_i != 1):
```python
special_indices = [i for i in range(n) if k[i] != 1]   # k = k_factors từ do_day_luoi_cua()
b_i = BoolVar cho mỗi special index                     # b_i=1 nếu x_i > 0
s = Σb_i                                                 # số loại đặc biệt có mặt trong pattern
# phân loại s: b0(s=0), b1(s=1), b2(s>=2) — đúng 1 trong 3 đúng
expr = Σ( round(100*(a_i + k_i)) * x_i )   # a=segment_sizes, k=k_factors, scale=100
ràng buộc theo case:
  s=0:  expr <= 100*(length - 60)
  s=1:  expr <= 100*(length - 0)
  s>=2: expr <= 100*(length - 15)
  luôn: expr >= 100*length*(1 - 0.01)     # hao hụt cố định 1%, KHÔNG cấu hình được qua form
```
→ Các hằng số `60 / 0 / 15` và `1%` hardcode cứng trong `cat_laser`, không expose ra form.

### B.2. Phân bổ (GĐ2) — `cat_laser_roi::solve_phase2()` (bản đầy đủ nhất, nên dùng làm chuẩn khi port)

```python
x_j ∈ IntVar[0, 2*Σdemands]   # số cây dùng pattern j, với mỗi pattern j trong patterns_df đã lọc

# Ràng buộc surplus mỗi loại đoạn i:
produced_i = Σ_j( x_j * pattern_j.segment_i )
s_i = produced_i - demand_i                  # có thể âm (thiếu) hoặc dương (thừa)
-max_surplus <= s_i <= max_surplus
abs_s_i = |s_i|                              # model.AddAbsEquality

# Giải lexicographic 3 bước (mỗi bước khoá kết quả bước trước làm ràng buộc cứng cho bước sau):
# Bước 1: MIN Σ(x_j * pattern_j.waste_mm)                        -> khoá == best
# Bước 2: MIN Σ(abs_s_i)  (tổng độ lệch tồn kho tuyệt đối)        -> khoá == best
# Bước 3 (nếu use_priority_constraint): MIN Σ(x_j * pattern_j.Priority_Score)
```

Lọc pattern trước khi đưa vào GĐ2:
```python
# use_priority_constraint=True: chỉ giữ pattern có ít nhất 1 đoạn kích thước >= 60mm
long_piece_indices = [i for i, length in enumerate(piece_lengths) if length >= 60]
patterns_df = patterns_df[ patterns_df[[f'segment_{i}' for i in long_piece_indices]].sum(axis=1) > 0 ]

# is_doan_cuoi (chế độ kết hợp Laser+Tự động) — nếu any(is_doan_cuoi) True:
selected = [i for i,sel in enumerate(is_doan_cuoi) if sel]
long_ticked  = [i for i in selected if piece_lengths[i] >= 60]
short_ticked = [(i, trunc(60/piece_lengths[i]) + 1) for i in selected if piece_lengths[i] < 60]
# pattern hợp lệ nếu THOẢ 1 TRONG 3:
#   (a) có ít nhất 1 đoạn dài (long_ticked) với segment_i >= 1
#   (b) có ít nhất 1 đoạn ngắn (short_ticked) với segment_i >= lower_bound (= trunc(60/size)+1)
#   (c) hao hụt của pattern >= 60mm (60 * SCALING_FACTOR ở đơn vị scaled)
```

Kết quả trả về (dict, dùng được trực tiếp — khuyến nghị expose thẳng qua API khi port):
```python
{
  'total_bars': int,
  'total_waste_mm': float,
  'waste_percentage': float,          # % trên tổng chiều dài đã dùng
  'total_surplus': int,               # Σ|s_i| tại nghiệm cuối
  'production_plan': DataFrame,       # pattern nào dùng bao nhiêu cây
  'summary_df': DataFrame             # Tên sắt | Đoạn(mm) | SL cần | SL cắt | Tồn kho
}
```

### B.3. Timer / time budget

- `time_limit_minutes` (input) → `time_limit_seconds = time_limit_minutes * 60`.
- GĐ2 của `cat_laser_roi` chạy **3 lần Solve() tuần tự** (3 mục tiêu lexicographic), mỗi lần dùng `solver.parameters.max_time_in_seconds = time_limit_seconds` → **tổng thời gian tối đa thực tế ≈ 3x time_limit_seconds** (biến `total_time_for_all_steps = time_limit_seconds * 3` dùng cho `SolverTimer` hiển thị đếm ngược ở FE).
- `cat_sat` GĐ2 chỉ chạy 1 lần `Solve()` với `max_time_in_seconds = time_limit_seconds` (không nhân 3, vì mục tiêu đã gộp chung 1 hàm `Minimize(Loss*W1 + Bundles*W2)`).

### B.4. Trọng số mục tiêu gộp (`cat_sat` GĐ2, khác cách tiếp cận lexicographic của `cat_laser_roi`)

```python
W1 = 10**6   # ưu tiên tuyệt đối cho hao hụt
W2 = 1       # tie-break phụ cho số bó/cây khi hao hụt bằng nhau
model.Minimize(Loss_expr * W1 + Bundles_expr * W2)
```
Đây là kỹ thuật **weighted-sum** (khác với `cat_laser_roi` dùng lexicographic 3 bước riêng biệt) — cho kết quả tương đương về mặt ưu tiên nhưng chỉ cần giải 1 lần thay vì 2-3 lần.

## C. Giao thức WebSocket (log real-time)

- Endpoint chuẩn (đang hoạt động, được `asgi.py` mount qua `iea_project/routing.py`):
  **`ws://<host>/ws/<app_name>/log/`** — với `app_name` ∈ `{cat_sat, cat_laser, cat_laser_roi}` — dùng chung 1 consumer (`iea_project/consumers.py::ChatConsumer`).
  - Group name nội bộ: `log_gurobi_solver_{app_name}` (khớp với `TeeStream(...)` trong từng `views.py`).
  - Khi client vừa connect, server gửi lại **toàn bộ lịch sử log** đã lưu trong biến global `LOG_HISTORY[group_name]` (list message) trước đó (nếu có phiên đang chạy) — giúp reconnect không mất log.
  - Format message gửi về: `{"message": "<string>"}` (text_data JSON, KHÔNG có `type`/`event` field).

- ⚠️ **Dead code phát hiện được**: `cat_laser_roi/consumers.py` (`LogConsumer`, group `log_solver_cat_laser_roi`) và `cat_laser_roi/routing.py` (`ws/cat_laser_roi/log/` qua `re_path`) **KHÔNG được mount vào `asgi.py`** (asgi.py chỉ import `iea_project.routing.websocket_urlpatterns`). Route `/ws/cat_laser_roi/log/` mà frontend thực sự gọi (`cat_laser_roi/templates/cat_laser_roi/index.html:182`) khớp với pattern generic `ws/<app_name>/log/` (app_name="cat_laser_roi") → dùng `ChatConsumer`, KHÔNG dùng `LogConsumer` riêng. File `consumers.py`/`routing.py` trong `cat_laser_roi/` là code thừa, an toàn để bỏ qua khi port.

**Các message đặc biệt (magic string) FE phải tự parse từ nội dung text**, không có structured event type:

| Message pattern | Nguồn phát | Ý nghĩa | FE xử lý |
|---|---|---|---|
| `"!CLEAR!"` | mọi module, trước khi in kết quả cuối | Xoá toàn bộ log cũ trên UI | `cat_sat`, `cat_laser_roi` index.html đều bắt chuỗi này để clear log panel |
| `"TIMER_UPDATE::{elapsed}::{total}"` | `SolverTimer.run()` (cat_sat + cat_laser_roi), in mỗi 1 giây | Cập nhật đồng hồ đếm ngược | parse `split("::")`, lấy elapsed/total để render progress bar |
| `"TESTING_LENGTH::{length}"` | `find_optimal_stock_length()` (chỉ cat_laser_roi) | Đang test chiều dài X trong vòng lặp dò tối ưu | FE cat_laser_roi highlight chiều dài đang test |
| `"OPTIMAL_LENGTH::{length}"` | `find_optimal_stock_length()` khi hoàn tất | Kết quả chiều dài tối ưu tìm được | FE hiển thị kết quả cuối |
| Chuỗi HTML thường (`<br>`, `<h4>`, bảng `<table class="table...">` từ `pandas.Styler.to_html()`) | các log `print()` khác | Nội dung log / bảng kết quả | FE `innerHTML +=` trực tiếp (server tự sinh HTML, KHÔNG phải JSON có cấu trúc) |

→ **Khi port sang Next.js**: nên thay cơ chế "in HTML rồi FE nối chuỗi" bằng emit **structured event** qua WebSocket (vd `{type: "progress", elapsed, total}`, `{type: "result", data: {...}}`) vì cách hiện tại (server generate HTML, FE chỉ nối chuỗi) không portable và khó test.

## D. Cache pattern (file-based)

- Thư mục: `patterns_cache/patterns_<cache_key>.pkl` (+ `patterns_<cache_key>_metadata.json`).
- `cache_key`:
  - `cat_sat`: MD5 của `json.dumps({length, segment_sizes, blade_width, te_dau_sat, hao_hut_percent}, sort_keys=True)`.
  - `cat_laser_roi`: SHA256 (16 ký tự đầu) của `{stock_length, piece_lengths, kerf_width, max_waste_percentage, trim_start, limit}`.
  - `cat_laser`: SHA256 (mặc định, không `use_md5`) của `{item_sizes (round 2 chữ số), item_waste_factors, stock_length (round 2 chữ số)}`.
- Nội dung pickle: `cat_sat` lưu `list[(obj_value: float, solution: list[int])]`; `cat_laser_roi` lưu `pandas.DataFrame` (cột `segment_0..N`, `Hao hụt (mm)`); `cat_laser` lưu `list[(tong_chieu_dai, solution_list, case_str)]`.
- **Không có TTL/invalidation tự động** ngoài thay đổi tham số đầu vào (hash khác → cache miss). Muốn xoá thủ công: xoá file trong `patterns_cache/`.

## E. Database Schema (Django models — chính xác theo `models.py`)

```python
# cat_sat/models.py
class Solution(models.Model):
    length = models.IntegerField()
    segment_sizes = models.JSONField()
    blade_width = models.FloatField()
    obj_value = models.FloatField()
    solution = models.JSONField()
# LƯU Ý: model này KHÔNG được ghi/đọc trong views.py hay optimization_logic.py hiện tại
# (pipeline chính dùng file cache pickle, không dùng bảng DB này) — có thể là bảng cũ/chưa dùng tới.

# accounts/models.py
class OTPCode(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='otp_code')
    secret_key = models.CharField(max_length=32, blank=True)   # tự sinh pyotp.random_base32() nếu rỗng
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

# optimization_logs/models.py
class OptimizationLog(models.Model):
    STATUS_CHOICES = [('success','OK'), ('error','Error'), ('timeout','Timeout')]
    MODULE_CHOICES = [('cat_sat','MC Tu Dong'), ('cat_laser_roi','MC Laser')]  # cat_laser KHÔNG có trong choices
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    module = models.CharField(max_length=30, choices=MODULE_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    duration_seconds = models.FloatField(null=True, blank=True)
    input_data = models.JSONField(default=dict)
    parameters = models.JSONField(default=dict)
    output_summary = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='success')
    error_message = models.TextField(blank=True, default='')
    class Meta: ordering = ['-created_at']
# cat_laser và cat_laser_roi (module) KHÔNG có models.py nào định nghĩa bảng riêng ngoài trên.
```

## F. Frontend hiện tại (để đối chiếu UX khi thiết kế lại)

- Thư viện bảng nhập liệu: **Handsontable** (spreadsheet-like input), dữ liệu autosave vào `localStorage` (`handsontable_data_cat_sat`, `handsontable_data`) để không mất khi reload trang.
- Cột bảng `cat_sat`: `['Tên sắt', 'Kích thước (mm)', 'SL Cần']` — 2 cột sau kiểu `numeric`.
- Cột bảng `cat_laser_roi`: `['Tên sắt', 'Kích thước (mm)', 'SL Cần', 'ĐOẠN CUỐI']` — cột cuối kiểu `checkbox` (map với `is_doan_cuoi` trong payload).
- Khi submit, FE lấy `hot.getData()`, lọc bỏ hàng toàn rỗng (`row.some(cell => cell !== null && cell !== '' && cell !== undefined)`), gửi nguyên mảng 2 chiều làm `pieces_data`.
- UI advanced settings (tìm chiều dài tối ưu) trong `cat_laser_roi/index.html` chỉ hiện khi tick checkbox `optimize_stock_length` (JS toggle show/hide).

## G. Danh sách bất nhất / rủi ro cần biết trước khi port

1. `cat_laser/views.py::optimize()` **không có `@login_required`** — khác 2 module còn lại (có thể là lỗ hổng bảo mật hoặc chủ ý bỏ qua vì module ít dùng).
2. `cat_laser_roi` response JSON qua HTTP **không mang dữ liệu kết quả có cấu trúc** — toàn bộ số liệu chỉ nằm trong HTML string bắn qua WebSocket. Muốn port sạch sang REST/Next.js **bắt buộc phải sửa `views.py`** để trả `result` dict (đã có sẵn ở `solve_phase2()`) qua JSON response thay vì chỉ `print()`.
3. `cat_sat/models.py::Solution` và `cat_laser_roi/consumers.py`+`routing.py` là **code không dùng tới** trong luồng hiện tại — không cần port.
4. `cat_sat/column_generator.py` là script demo độc lập (xem mục 3.6 phần thân tài liệu) — không phải logic production.
5. `use_priority_constraint`/`priorities_list` trong `cat_laser_roi` hiện luôn bị set `0`/tắt ở tầng nghiệp vụ hiện dùng (theo comment trong `views.py`: `# Priority disabled, always 0`) dù code solver vẫn hỗ trợ đầy đủ — cân nhắc có cần port tính năng này hay bỏ.
6. Hằng số hardcode không expose qua form: `cat_laser` — hao hụt cố định 1% và các mốc 60/0/15mm (mục B.1); `SCALING_FACTOR` khác nhau giữa các module (10 ở `cat_sat`/`cat_laser_roi`, 100 ở `cat_laser`) — cần thống nhất đơn vị khi viết lại.

---
---
# PHẦN II — CÁCH TÍNH HAO HỤT & VÍ DỤ THỰC TẾ (MC Laser & Đề xuất thanh sắt)

> Phần này gộp toàn bộ giải thích **cách tính hao hụt** của **MC Laser** (`cat_laser_roi`) và màn **Đề xuất thanh sắt** (`cat_sat/de_xuat_*.py`), kèm ví dụ số thật **500 bộ Bàn J55**.
>
> **Lưu ý quan trọng:** số liệu Đề xuất dưới đây tính theo **code hiện tại** — đã **đồng bộ cách tính hao hụt với MC Laser: KHÔNG tính lưỡi cắt (kerf) vào hao hụt** (sửa ở `de_xuat_logic.py`, hàm `generate_patterns`). Vì vậy các con số ở đây **thay thế** tài liệu cũ `GIAI_THICH_TINH_TOAN_DE_XUAT.md` (bản đó tính lúc còn gộp lưỡi cắt vào hao hụt, % nhỉnh hơn).

## II.1. Bốn thành phần của một cây sắt & các khái niệm gốc

Mỗi cây sắt nguyên khi cắt sẽ tan thành **4 phần**. Hiểu rõ 4 phần này là hiểu toàn bộ cách tính hao hụt/tồn kho.

```
│◄────────────────────── cây sắt (vd 6000mm) ──────────────────────►│
│▓▓│ [660] ✂ [660] ✂ [660] ✂ ... ✂ [660] │░░░░░│
 ↑    ↑        ↑                              ↑
 ①    ②        ③ lưỡi cắt (mỗi nhát ~1mm)   ④ khúc thừa đuôi
 tề   đoạn tốt
 đầu
```

| # | Thành phần | Là gì | Số lần/cây | Vào hao hụt? |
|---|---|---|---|---|
| ① | **Tề đầu (trim)** | Xén bỏ đầu cây (méo/gỉ), cố định (vd 10mm) | 1 lần | **CÓ** |
| ② | **Sắt thành đoạn** | Đoạn đúng kích thước, dùng làm sản phẩm | — | Không (là thành phẩm) |
| ③ | **Lưỡi cắt (kerf)** | Bề rộng lưỡi/tia nghiền sắt thành mạt mỗi nhát (~1mm) | nhiều lần (theo số đoạn) | **KHÔNG** (coi là "đã dùng") |
| ④ | **Khúc thừa đuôi** | Đầu mẩu cuối cây, quá ngắn không cắt thêm được | 1 lần | **CÓ** |

Ngoài ra còn khái niệm **đoạn dư (tồn kho)** — KHÔNG nằm trên 1 cây riêng lẻ mà là **tổng hợp toàn kế hoạch**:

- **Đoạn dư (tồn kho)** = những đoạn ② **nguyên vẹn, đúng kích thước** nhưng **cắt lố** so với nhu cầu (vì phải mua nguyên cây, không mua lẻ). Là **sắt tốt cất kho dùng lô sau** → **KHÔNG tính vào hao hụt**.

**Hai công thức chốt (dùng cho CẢ MC Laser và Đề xuất hiện tại):**

```
Hao hụt/cây  =  chiều dài cây − sắt thành đoạn − lưỡi cắt      (= tề đầu + khúc thừa đuôi)
Hao hụt %    =  Σ(hao hụt/cây × số cây)  ÷  Σ(chiều dài cây × số cây)  × 100
Đoạn dư      =  (tổng đoạn cắt ra)  −  (nhu cầu)               → tách riêng, KHÔNG vào %
```

## II.2. MC Laser (`cat_laser_roi`) tính hao hụt như thế nào

### II.2.1. Công thức (trích code)

Nguồn: `cat_laser_roi/optimization_logic.py`.

```python
# GĐ1 — hao hụt mỗi pattern (dòng ~110-113):
Tong_Material = Σ(đoạn) + Σ(số đoạn) × kerf          # đoạn + lưỡi cắt  (KHÔNG gồm tề đầu)
Hao hụt (mm)  = stock_length − Tong_Material         # = tề đầu + khúc thừa đuôi

# GĐ2 — hao hụt cả kế hoạch (dòng ~762, 768):
final_waste = Σ( Hao_hụt_pattern × SL_cây_pattern )
waste_%     = final_waste / (chiều_dài_cây × tổng_cây) × 100
```

→ **Lưỡi cắt bị loại khỏi hao hụt** (nằm trong `Tong_Material` = "sắt đã dùng"). Tề đầu và khúc thừa đuôi thì tính vào.

### II.2.2. Ví dụ số (cây 6000mm, đoạn 660mm, tề đầu 10, lưỡi cắt 1)

Một cây cắt 9 đoạn 660 (`6000 ÷ 660 = 9,09 → 9`):

```
② Sắt thành đoạn: 9 × 660 = 5.940mm
① Tề đầu:                 =    10mm
③ Lưỡi cắt:       9 × 1   =     9mm
④ Khúc thừa đuôi:         =    41mm
──────────────────────────────────
Cộng:        5.940+10+9+41 = 6.000mm ✔

Hao hụt/cây MC Laser = 6000 − 5940 − 9 = 51mm   (= tề đầu 10 + khúc thừa 41)
```

### II.2.3. Tồn kho của MC Laser: cho phép cả THỪA và THIẾU

Ràng buộc tồn kho (dòng ~647-653): `s_i = sản_xuất_i − nhu_cầu_i` với **`−max_surplus ≤ s_i ≤ max_surplus`** → **cho phép s_i ÂM (thiếu)**.

- **Số dương** = thừa (cắt lố) → cất kho.
- **Số âm** = **thiếu** (cắt hụt nhu cầu) → phải bù lô sau.
- `max_surplus` mặc định = **10** (form `cat_laser_roi/forms.py`, `initial=10`), người dùng **chỉnh tay** để tìm nghiệm.

**Vì sao phải cho lệch (không ép = 0):** ép mọi tồn kho = 0 nghĩa là bắt số cây nguyên cắt ra **khớp tuyệt đối** nhu cầu mọi cỡ cùng lúc — điều kiện Diophantine cực chặt, **hầu hết vô nghiệm**. Ví dụ cần 3195 đoạn, mỗi cây ra 8 → `3195/8 = 399,4` không có số cây nguyên nào ra đúng 3195. Nên phải cho dư/thiếu vài đoạn mới giải được. (Đây là xác nhận của chính người viết MC Laser.)

## II.3. Đề xuất thanh sắt — tính toán đầy đủ (ví dụ 500 bộ J55)

> Bài toán 2 tầng độc lập với MCTĐ/MC Laser (`cat_sat/de_xuat_logic.py`). Tầng 1: bung định mức → nhu cầu. Tầng 2: mỗi loại sắt chọn chiều dài + số cây, cắt TRỘN mọi cỡ, min khúc thừa.

### II.3.1. Đầu vào

**Tham số:** số bộ = 500 · tề đầu = 10mm · lưỡi cắt = 1mm · hao hụt tối đa = 1% · cho phép chênh lệch = 10 đoạn · chiều dài chuẩn = {5850, 6000} · dải tự dò = 5000→7000 bước 10.

**Định mức 1 bộ Bàn J55:**

| Công đoạn | SL mảnh/bộ | Nguyên liệu | Quy cách | Dài cắt (mm) | SL/mảnh |
|---|---|---|---|---|---|
| chân bàn | 4 | sắt vuông | 50×50 | 660 | 1 |
| chân bàn | 4 | sắt hộp | 25×50 | 200 | 1 |
| đoạn dài | 2 | sắt hộp | 25×50 | 930 | 1 |
| đoạn ngắn | 2 | sắt hộp | 25×50 | 765 | 1 |
| giằng bàn | 1 | sắt vuông | 20×20 | 840 | 1 |
| viền bàn | 2 | sắt hộp | 25×50 | 695 | 1 |

### II.3.2. Tầng 1 — Bung định mức thành nhu cầu

```
Nhu cầu 1 cỡ đoạn = (SL mảnh/bộ) × (SL/mảnh) × (số bộ)
```

Gom **theo quy cách** (cùng tiết diện cắt chung được) → **3 loại sắt**:

| Loại sắt | Các cỡ (mm) | Nhu cầu |
|---|---|---|
| sắt vuông 50×50 | 660 | 2000 |
| sắt hộp 25×50 | 930 / 765 / 695 / 200 | 1000 / 1000 / 1000 / 2000 |
| sắt vuông 20×20 | 840 | 500 |

### II.3.3. Tầng 2 — với mỗi loại: kiểu cắt, chọn chiều dài, giải tối ưu

**Kiểu cắt hợp lệ** (1 cây): `Σ(số đoạn × dài đoạn) + Σ(số đoạn) × lưỡi cắt ≤ chiều dài cây − tề đầu`.

**Chọn chiều dài:** chấm các **chiều dài chuẩn** trước; nếu có cái ≤ ngưỡng % thì chốt (khỏi vét cạn); nếu không → **vét cạn** cả dải, lấy cái ít khúc thừa nhất. (Chi tiết vì sao nhanh mà vẫn chính xác: xem II.5.)

**Bài toán tối ưu (OR-Tools CP-SAT), mỗi loại:**
- Biến: số cây dùng mỗi kiểu cắt (nguyên ≥ 0).
- Ràng buộc mỗi cỡ: `nhu cầu ≤ tổng cắt ra ≤ nhu cầu + chênh lệch` (**cắt đủ, KHÔNG cho thiếu** — khác MC Laser).
- Mục tiêu: `min Σ(khúc thừa/cây × số cây)`.

### II.3.4. Kết quả từng loại (số thật, code hiện tại)

**① sắt hộp 25×50 — chọn 6000mm, 467 cây, hao hụt 0.18%** (chi tiết nhất, 4 cỡ):

Bộ giải chọn 3 kiểu cắt (ô trống = 0):

| Thanh | 930 | 765 | 695 | 200 | Số cây | HH/cây |
|---|---|---|---|---|---|---|
| 6000 | 4 | 1 | 1 | 4 | 200 | 10 |
| 6000 | 1 | 4 | 2 | 3 | 200 | 10 |
| 6000 | · | · | 6 | 9 | 67 | 15 |

Kiểm chứng (cộng theo cột) & tồn kho:

| Cỡ | Cần | Cắt ra | Dư |
|---|---|---|---|
| 930 | 1000 | 4×200 + 1×200 = **1000** | 0 |
| 765 | 1000 | 1×200 + 4×200 = **1000** | 0 |
| 695 | 1000 | 1×200 + 2×200 + 6×67 = **1002** | +2 |
| 200 | 2000 | 4×200 + 3×200 + 9×67 = **2003** | +3 |

```
HH/cây kiểu A = 6000 − (4·930+1·765+1·695+4·200) − 10 nhát×1 = 6000 − 5980 − 10 = 10mm
Tổng khúc thừa = 10×200 + 10×200 + 15×67 = 5.005mm
Tổng mua       = 6000 × 467 = 2.802.000mm
Hao hụt %      = 5.005 ÷ 2.802.000 × 100 = 0,18%     (so sánh chuẩn: 6000→0.18%, 5850→0.30%)
```

**② sắt vuông 50×50 — chọn 6000mm, 223 cây, hao hụt 0.85%:**
```
9 đoạn 660/cây, HH/cây = 6000 − 5940 − 9 = 51mm
Cần 2000, cắt ra 223×9 = 2007 → dư 7 (tồn kho)
Khúc thừa = 223×51 = 11.373mm ;  % = 11.373 ÷ 1.338.000 = 0,85%
(so sánh chuẩn: 6000→0.85%, 5850→9.61%)
```

**③ sắt vuông 20×20 — VÉT CẠN ra 6740mm, 63 cây, hao hụt 0.18%:**
```
Chiều dài chuẩn đều quá cao (6000→1.88%, 5850→13.74%) → vượt ngưỡng 1% → vét cạn dải
Vét cạn 5000→7000 bước 10 → tốt nhất 6740mm: 8 đoạn 840/cây, HH/cây 12mm
Cần 500, cắt ra 63×8 = 504 → dư 4 ;  khúc thừa 63×12 = 756mm ;  % = 756 ÷ 424.620 = 0,18%
```

### II.3.5. Tổng hợp cả đơn hàng (500 bộ)

| Loại sắt | Chiều dài | Số cây | Tổng mua | Khúc thừa | % | Dư |
|---|---|---|---|---|---|---|
| sắt vuông 50×50 | 6000 | 223 | 1.338.000 mm | 11.373 mm | 0.85% | 7 |
| sắt hộp 25×50 | 6000 | 467 | 2.802.000 mm | 5.005 mm | 0.18% | 5 |
| sắt vuông 20×20 | 6740 | 63 | 424.620 mm | 756 mm | 0.18% | 4 |
| **TỔNG** | | **753** | **4.564.620 mm ≈ 4.564,6 m** | **17.134 mm ≈ 17,13 m** | **0.375%** | |

```
Hao hụt toàn đơn = 17.134 ÷ 4.564.620 × 100 ≈ 0,375%
```

## II.4. So sánh MC Laser vs Đề xuất

| Tiêu chí | MC Laser (`cat_laser_roi`) | Đề xuất (`cat_sat/de_xuat`) |
|---|---|---|
| **Mục đích** | Tìm **chiều dài cây tối ưu** cho **1 loại sắt** | Đề xuất **mua vật tư cho cả sản phẩm** (mọi loại) |
| **Phạm vi 1 lần chạy** | 1 loại sắt | Cả định mức → chạy tuần tự từng loại |
| **Hao hụt = khúc thừa/cây** | ✔ (tề đầu + khúc thừa đuôi) | ✔ **giống hệt** |
| **Lưỡi cắt (kerf) vào hao hụt?** | **Không** | **Không** (đã đồng bộ) |
| **Đoạn dư (tồn kho) vào %?** | Không (cột riêng) | Không (cột riêng) |
| **Cho phép THIẾU (số âm)?** | **Có** (±max_surplus) | **Không** (chỉ dư 0…max_surplus) |
| **Chọn chiều dài** | Luôn **vét cạn** dải (bước 10mm) | **Chuẩn trước**, đạt ngưỡng thì khỏi vét |
| **Số lần giải solver/chiều dài** | ×3 (lexicographic) | ×1 (gộp 1 mục tiêu) |
| **Pattern/lần** | tới 100.000 | vài trăm (lọc chặt) |
| **Dựng model** | pandas `.iloc` (chậm) | list/tuple thuần |
| **Realtime/HTML/Redis** | Có (WebSocket) | Không (chỉ trả số) |
| **Tốc độ** | phút → giờ | vài giây |

**Ví dụ khác biệt "thiếu vs dư"** — cần 3195 đoạn 700mm, cây 6000 (8 đoạn/cây):

- **MC Laser** (cho thiếu): chọn **399 cây** = 3192 → **thiếu 3** (ít cây nhất, hao hụt sàn), giao thiếu bù sau.
- **Đề xuất** (không thiếu): buộc **400 cây** = 3200 → **dư 5** (đủ hàng, dư cất kho).

## II.5. Vì sao Đề xuất nhanh (vài giây) mà vẫn chính xác

Nhanh do **bỏ việc thừa**, không phải tính ẩu — phần chọn số cây vẫn giải tối ưu bằng OR-Tools:

| Mẹo | Nội dung | Vì sao không sai |
|---|---|---|
| Bỏ vét cạn nếu chuẩn đã đạt | Chiều dài chuẩn ≤ ngưỡng → chốt luôn | Đằng nào cũng mua chuẩn đó; đã đạt thì quét thêm vô ích |
| Chỉ bỏ kiểu cắt QUÁ phí | Giữ mọi kiểu khúc thừa ≤ 60% cây | Kiểu phí >60% không bao giờ được chọn ở lời giải tối ưu |
| Bài toán nhỏ | Mỗi loại vài cỡ đoạn | Nhỏ thì giải nhanh là đương nhiên |

Cấu hình ưu tiên chính xác: liệt kê **toàn bộ** kiểu cắt (giới hạn 200.000, thực tế chỉ vài trăm–vài nghìn), chấm chuẩn & vét cạn **đều giải chính xác từng chiều dài** → kết quả mỗi loại là **tối ưu tuyệt đối** trong dải đã cho. Muốn tìm kỹ hơn: mở rộng dải min/max, thu nhỏ bước dò (10mm), tăng thời gian chạy tối đa.



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

---

# PHẦN III — PUBLIC API CHO HỆ THỐNG ERP

> Mục đích: ERP backend gọi tới `cat_sat_iea` để **tính toán đề xuất thanh sắt**, sau đó tự lưu kết quả vào DB của ERP. `cat_sat_iea` đóng vai trò **solver service stateless** (chỉ tính, không lưu).

## III.1. Endpoint duy nhất

**`POST /api/v1/de_xuat/propose/`**

Bung định mức sản phẩm (BOM) + tối ưu chiều dài mua + số cây mỗi loại sắt. **Gộp 2 bước (materials + optimize từng loại) thành 1 request duy nhất**, trả kết quả toàn bộ.

---

## III.2. Request — Fields cần truyền

### Header
```
POST /api/v1/de_xuat/propose/ HTTP/1.1
Content-Type: application/json
```

### Body (JSON)

```jsonc
{
  // ====== Tầng 1: Định mức sản phẩm ======
  "num_sets": 500,                     // int ≥ 1 — bắt buộc — số bộ sản xuất
  
  "bom": [                             // list — bắt buộc — định mức sản phẩm
    {
      "part": "chân bàn",              // str, tên mảnh công đoạn
      "qty_per_set": 4,                // int, số lượng mảnh/bộ
      "material": "sắt vuông",         // str — bắt buộc — nguyên liệu (gom theo quy cách)
      "spec": "50×50",                 // str, quy cách/kích thước tiết diện
      "cut_length": 660.0,             // float — bắt buộc — chiều dài cắt (mm)
      "qty_per_part": 1                // int, số đoạn/mảnh (mặc định 1)
    },
    {
      "part": "chân bàn",
      "qty_per_set": 4,
      "material": "sắt hộp",
      "spec": "25×50",
      "cut_length": 200.0,
      "qty_per_part": 1
    },
    {
      "part": "đoạn dài",
      "qty_per_set": 2,
      "material": "sắt hộp",
      "spec": "25×50",
      "cut_length": 930.0,
      "qty_per_part": 1
    }
    // ... thêm các mảnh khác
  ],

  // ====== Tầng 2: Tham số tối ưu ======
  "stock_lengths": [5850, 6000, 7000], // int[] — bắt buộc — các chiều dài thanh cố định (mm)
  "trim_start": 10,                    // int, tề đầu sắt (mm), mặc định 10
  "blade_width": 1.0,                  // float, độ rộng lưỡi cắt/kerf (mm), mặc định 1.0
                                        //   ⚠ Server làm tròn LÊN thành số nguyên (math.ceil) trước khi đưa
                                        //   vào solver — CP-SAT không nhận hệ số float trong constraint.
                                        //   VD: 1.2 -> 2, 2.5 -> 3. Nên truyền số nguyên để tránh bất ngờ.
  "max_waste_percentage": 1.0,         // float, ngưỡng % hao hụt mỗi loại sắt (mặc định 1.0)
  "max_surplus": 10,                   // int, cho phép chênh lệch ± mỗi cỡ đoạn (mặc định 10)
  
  // Auto-scan (nếu chiều dài chuẩn không đạt ngưỡng)
  "min_length": 4000,                  // int, dải min (mm), mặc định 4000
  "max_length": 12000,                 // int, dải max (mm), mặc định 12000
  "length_step": 50,                   // int, bước quét (mm), mặc định 50
  
  // Solver
  "time_limit_seconds": 480            // int, tối đa cho mỗi lần giải (s), mặc định 480
}
```

### Validation Rules
- `num_sets` ≥ 1
- `bom` không trống, mỗi row phải có `cut_length` và `material` (bỏ row rỗng/thiếu)
- `stock_lengths` không trống, ≥ 100mm
- `max_waste_percentage` ≥ 0
- `max_surplus` ≥ 0
- `min_length` ≥ 100
- `max_length` ≥ `min_length`

---

## III.3. Response — Cấu trúc trả về (Success)

**HTTP 200 OK**

```jsonc
{
  "status": "success",

  // ====== Tóm tắt toàn bộ đơn hàng ======
  "summary": {
    "num_sets": 500,                        // số bộ
    "num_material_groups": 3,               // số loại sắt (gom theo quy cách)
    "total_bars_all": 753,                  // tổng số cây mua toàn bộ
    "total_purchased_mm": 4564620,          // tổng vật liệu mua (mm)
    "total_waste_mm": 17134,                // tổng khúc thừa (phế liệu) — KHÔNG tính đoạn dư
    "total_surplus_pieces": 16,             // tổng đoạn dư (tồn kho)
    "waste_percentage": 0.375,              // % hao hụt chung (khúc thừa / tổng mua)
    "any_over_threshold": false             // true nếu có loại vượt max_waste_percentage
  },

  // ====== Đề xuất mua từng loại sắt ======
  "purchase_plan": [
    {
      // === Thông tin loại sắt ===
      "material": "sắt vuông 50×50",        // tên loại (gom từ material+spec)
      "feasible": true,                     // true=giải được, false=không khả thi
      
      // === Kết quả chọn ===
      "best_stock_length": 6000,            // chiều dài thanh tối ưu (mm)
      "length_source": "fixed",             // "fixed" (chiều dài chuẩn) hay "scanned" (vét cạn)
      "total_bars": 223,                    // số cây phải mua loại này
      "total_purchased_mm": 1338000,        // tổng mua = best_stock_length × total_bars
      "total_waste_mm": 11373,              // tổng khúc thừa (phế liệu)
      "waste_percentage": 0.85,             // % hao hụt loại này
      "total_surplus_pieces": 7,            // tổng đoạn dư (tồn kho)
      "over_threshold": false,              // true nếu waste_pct vượt max_waste_percentage
      "max_waste_pct_threshold": 1.0,       // ngưỡng đã dùng
      
      // === Chi tiết theo cỡ đoạn ===
      "pieces": [
        {
          "size": 660,                      // cỡ đoạn (mm)
          "demand": 2000,                   // cần
          "produced": 2007,                 // cắt ra thực tế
          "surplus": 7                      // thừa (produced - demand)
        }
      ],
      
      // === Kế hoạch cắt chi tiết ===
      "cutting_patterns": [
        {
          "pattern_id": 1,
          "stock_length": 6000,             // chiều dài thanh
          "counts": [9],                    // số lượng từng cỡ: [660mm: 9 đoạn]
          "bars": 223,                      // số cây làm pattern này
          "waste_per_bar": 51,              // hao hụt/cây (mm) = tề đầu + khúc thừa
          "pieces_breakdown": [
            {"size": 660, "count": 9}
          ]
        }
      ],
      
      // === So sánh các chiều dài (để hiển thị trên UI) ===
      "length_comparison": [
        {"length": 5850, "bars": 227, "waste_pct": 9.61},
        {"length": 6000, "bars": 223, "waste_pct": 0.85}   // ← được chọn
      ],
      "optimal_custom_length": null         // chiều dài tối ưu nếu vét cạn (không null khi scanned)
    },
    {
      // === Loại sắt 2 ===
      "material": "sắt hộp 25×50",
      "feasible": true,
      "best_stock_length": 6000,
      "length_source": "fixed",
      "total_bars": 467,
      "total_purchased_mm": 2802000,
      "total_waste_mm": 5005,
      "waste_percentage": 0.18,
      "total_surplus_pieces": 5,
      "pieces": [
        {"size": 930, "demand": 1000, "produced": 1000, "surplus": 0},
        {"size": 765, "demand": 1000, "produced": 1000, "surplus": 0},
        {"size": 695, "demand": 1000, "produced": 1002, "surplus": 2},
        {"size": 200, "demand": 2000, "produced": 2003, "surplus": 3}
      ],
      "cutting_patterns": [
        {
          "pattern_id": 1,
          "stock_length": 6000,
          "counts": [4, 1, 1, 4],           // 930×4, 765×1, 695×1, 200×4
          "bars": 200,
          "waste_per_bar": 10,
          "pieces_breakdown": [
            {"size": 930, "count": 4},
            {"size": 765, "count": 1},
            {"size": 695, "count": 1},
            {"size": 200, "count": 4}
          ]
        },
        {
          "pattern_id": 2,
          "stock_length": 6000,
          "counts": [1, 4, 2, 3],
          "bars": 200,
          "waste_per_bar": 10
        },
        {
          "pattern_id": 3,
          "stock_length": 6000,
          "counts": [0, 0, 6, 9],
          "bars": 67,
          "waste_per_bar": 15
        }
      ],
      "length_comparison": [
        {"length": 5850, "bars": 475, "waste_pct": 0.30},
        {"length": 6000, "bars": 467, "waste_pct": 0.18}
      ],
      "optimal_custom_length": null
    },
    {
      // === Loại sắt 3 (vét cạn) ===
      "material": "sắt vuông 20×20",
      "feasible": true,
      "best_stock_length": 6740,           // đặt bất kỳ (không phải chuẩn)
      "length_source": "scanned",
      "total_bars": 63,
      "total_purchased_mm": 424620,
      "total_waste_mm": 756,
      "waste_percentage": 0.18,
      "total_surplus_pieces": 4,
      "pieces": [
        {"size": 840, "demand": 500, "produced": 504, "surplus": 4}
      ],
      "cutting_patterns": [
        {
          "pattern_id": 1,
          "stock_length": 6740,
          "counts": [8],
          "bars": 63,
          "waste_per_bar": 12,
          "pieces_breakdown": [{"size": 840, "count": 8}]
        }
      ],
      "length_comparison": [
        {"length": 5850, "bars": 72, "waste_pct": 13.74},
        {"length": 6000, "bars": 67, "waste_pct": 1.88}
      ],
      "optimal_custom_length": 6740        // gợi ý chiều dài đặt riêng
    }
  ],

  // ====== Echo input (để ERP lưu audit) ======
  "input_echo": {
    "num_sets": 500,
    "stock_lengths": [5850, 6000, 7000],
    "trim_start": 10,
    "blade_width": 1,                  // đã làm tròn lên (ceil) từ input gốc, luôn là số nguyên
    "max_waste_percentage": 1.0,
    "max_surplus": 10,
    "min_length": 4000,
    "max_length": 12000,
    "length_step": 50
  },

  "calculation_time_seconds": 12.4        // thời gian solver chạy
}
```

---

## III.4. Response — Lỗi

### 400 Bad Request (dữ liệu sai)
```jsonc
{
  "status": "error",
  "code": "INVALID_INPUT",
  "message": "Định mức rỗng hoặc không hợp lệ"
}
```

### 422 Unprocessable Entity (không tìm được giải pháp)
```jsonc
{
  "status": "error",
  "code": "NO_FEASIBLE_SOLUTION",
  "message": "Không có cách cắt nào đạt hao hụt ≤ 1.0% với các chiều dài đã cho. Hãy tăng dung sai hoặc tăng dải tự dò.",
  "failing_materials": ["sắt vuông 20×20"]
}
```

### 500 Internal Server Error (lỗi solver)
```jsonc
{
  "status": "error",
  "code": "SOLVER_ERROR",
  "message": "Lỗi nội bộ solver",
  "traceback": "..."  // chỉ khi DEBUG=True
}
```

---

## III.5. Các trường cần ERP BE lưu vào Database

Vì `cat_sat_iea` không lưu, **ERP BE phải lưu** các field này:

```sql
-- Bảng ProposalResult (trong DB của ERP)
CREATE TABLE proposal_result (
  id INT PRIMARY KEY,
  user_id INT,                          -- người tạo yêu cầu
  proposal_date DATETIME,               -- khi tính đề xuất
  
  -- Input
  num_sets INT,                         -- số bộ
  bom_input JSON,                       -- toàn bộ BOM gốc (để tái tạo)
  stock_lengths_input JSON,             -- [5850, 6000, ...]
  trim_start INT,
  blade_width FLOAT,
  max_waste_pct FLOAT,
  max_surplus INT,
  
  -- Output tóm tắt
  total_bars_all INT,                   -- tổng số cây mua
  total_purchased_mm INT,               -- tổng mm mua
  total_waste_mm INT,                   -- khúc thừa
  total_surplus_pieces INT,             -- đoạn dư
  waste_percentage FLOAT,               -- %
  any_over_threshold BOOLEAN,
  
  -- Chi tiết
  purchase_plan JSON,                   -- toàn bộ purchase_plan[] từ API response
  
  -- Meta
  calculation_time_seconds FLOAT,
  status VARCHAR(20),                   -- 'success' / 'error'
  error_message TEXT
);
```

**Tối thiểu ERP cần lưu:**
- `bom_input` (input gốc, để kiểm tra lại)
- `purchase_plan` (kết quả chi tiết)
- `summary` (tóm tắt: total_bars, waste_pct, ...)
- `proposal_date` & `user_id` (audit trail)

---

## III.6. Ví dụ gọi API từ ERP Backend (Python)

```python
import requests
import json

# ERP backend gọi solver
def call_de_xuat_api(num_sets, bom, stock_lengths, trim=10):
    url = "http://cat_sat_iea_server:8000/api/v1/de_xuat/propose/"
    
    payload = {
        "num_sets": num_sets,
        "bom": bom,
        "stock_lengths": stock_lengths,
        "trim_start": trim,
        "blade_width": 1.0,
        "max_waste_percentage": 1.0,
        "max_surplus": 10,
        "min_length": 4000,
        "max_length": 12000,
        "length_step": 50,
        "time_limit_seconds": 480
    }
    
    try:
        resp = requests.post(url, json=payload, timeout=600)  # 10 phút max
        result = resp.json()
        
        if resp.status_code == 200 and result["status"] == "success":
            # Lưu result vào DB ERP
            save_proposal_to_db(num_sets, payload, result)
            return result
        else:
            # Handle error
            print(f"API error: {result.get('message')}")
            return None
    except Exception as e:
        print(f"Request failed: {e}")
        return None

# Lưu result vào DB
def save_proposal_to_db(num_sets, input_payload, api_response):
    proposal = ProposalResult(
        user_id=current_user.id,
        num_sets=num_sets,
        bom_input=input_payload["bom"],
        purchase_plan=api_response["purchase_plan"],
        total_bars_all=api_response["summary"]["total_bars_all"],
        waste_percentage=api_response["summary"]["waste_percentage"],
        status="success"
    )
    proposal.save()
```

---

## III.7. Ghi chú quan trọng

### Hao hụt = Phế liệu (khúc thừa/cây)
- **Công thức:** hao hụt/cây = chiều dài cây − sắt thành đoạn − lưỡi cắt (= tề đầu + khúc thừa đuôi)
- **KHÔNG tính lưỡi cắt vào %** (kerf coi là "sắt đã dùng")
- **Đoạn dư (tồn kho) KHÔNG vào %** — lưu riêng để ERP quản lý

### Thứ tự ưu tiên chiều dài
1. **Chiều dài chuẩn** (`stock_lengths`) — chấm đầu tiên
   - Nếu đạt ngưỡng % → chốt, khỏi vét cạn
   - Nếu không đạt → sang bước 2
2. **Vét cạn** (`min_length` → `max_length`, bước `length_step`)
   - Lọc các chiều dài trong dải
   - Giải chính xác từng chiều dài → lấy hao hụt thấp nhất
3. **Fallback** — nếu cả 2 không khả thi
   - Trả `feasible: false` + reason

### Timeout & Performance
- `time_limit_seconds` áp dụng cho **mỗi lần giải solver**
- Số lần giải = số loại sắt × (1 lần chấm + N lần vét cạn nếu cần)
- Ví dụ: 3 loại sắt × ~50 lần vét cạn mỗi loại = ~150 lần → **tối đa ~150 × 480s** (rất dài)
  - **Khuyến nghị:** giới hạn `time_limit_seconds` = 8–30s cho production

---
