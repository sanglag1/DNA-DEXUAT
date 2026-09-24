# DNA-DEXUAT — Đề xuất thanh sắt

Ứng dụng web tính **vật tư sắt cần mua** từ định mức sản phẩm (BOM): nhập định mức và số bộ cần sản xuất, hệ thống tự tính mỗi loại sắt cần mua bao nhiêu cây, chiều dài nào, cắt theo kiểu nào để tổng sắt mua ít nhất.

Bài toán nền tảng là **Cutting Stock 1 chiều**, giải bằng Google OR-Tools (CP-SAT).

---

## Nguồn gốc

Repo này phát triển dựa trên hệ thống **Cắt sắt IEA** của [Duy-Vuong Tran](https://github.com/vuongcris4) — [cat_sat_iea](https://github.com/vuongcris4/cat_sat_iea), xây dựng cho nhà máy nội thất mây tre xuất khẩu.

Phần bổ sung trong repo này là module **Đề xuất thanh sắt** (`cat_sat/de_xuat_*`) và **API tích hợp ERP** (`api/`).

---

## Ba module

| Module | Đường dẫn | Vai trò |
|---|---|---|
| **MCTĐ** | `/cat_sat/` | Tối ưu cắt cho máy cắt tự động |
| **MC Laser** | `/cat_laser_roi/` | Tối ưu cắt cho máy laser, có dò chiều dài cây tối ưu |
| **Đề xuất thanh sắt** | `/cat_sat/de_xuat/` | Tính vật tư cần mua cho cả sản phẩm (module bổ sung) |

Ba module dùng chung Django project và thư viện OR-Tools, nhưng **logic tối ưu độc lập** — sửa module này không ảnh hưởng module kia.

---

## Module Đề xuất thanh sắt

### Bài toán 2 tầng

1. **Bung định mức** — từ BOM sản phẩm và số bộ, tính ra nhu cầu số đoạn theo từng loại sắt (gom theo quy cách)
2. **Tối ưu mua** — với mỗi loại sắt: chọn chiều dài cây và số cây sao cho tổng khúc thừa nhỏ nhất

### Điểm khác so với MC Laser

| | MC Laser | Đề xuất thanh sắt |
|---|---|---|
| Mục đích | Tối ưu cắt 1 loại sắt đã có | Tính vật tư cần **mua** cho cả sản phẩm |
| Giao hàng | Cho phép cắt **thiếu** (nợ hàng) | **Luôn đủ**, chỉ được dư |
| Chọn chiều dài | Luôn vét cạn dải | Ưu tiên chiều dài **mua được**, chỉ vét cạn khi cần |

### Một số cơ chế đáng chú ý

- **Giới hạn 4 cỡ đoạn/cây** — vừa tăng tốc giải, vừa dễ thực thi ở xưởng. Đã kiểm chứng không làm mất nghiệm tối ưu trên BOM thật.
- **Chuẩn hoá quy cách** — `10*20`, `10X20`, `10 × 20` quy về `10x20` để không tách nhầm thành nhiều lô mua.
- **Tách bạch hết giờ với vô nghiệm** — solver hết thời gian và bài toán thật sự không có lời giải là hai việc khác nhau, không gộp chung.

### Kiểm chứng

Đối chiếu với MC Laser trên cùng dữ liệu (BOM ghế tình yêu, 500 bộ, 6 nhóm vật tư): **hao hụt khớp tuyệt đối ở cả 6 nhóm**. Hai thuật toán viết độc lập cho cùng kết quả.

---

## Công nghệ

| Thành phần | Dùng gì |
|---|---|
| Backend | Python 3.11, Django 5.1 |
| Bộ giải tối ưu | Google OR-Tools 9.15 (CP-SAT) |
| CSDL | PostgreSQL (production) / SQLite (dev) |
| Realtime | Django Channels + Redis |
| Frontend | Django Templates, Bootstrap, Handsontable |
| Đóng gói | Docker Compose |

---

## Chạy trên máy

```bash
git clone https://github.com/sanglag1/DNA-DEXUAT.git
cd DNA-DEXUAT

# Chạy bằng Docker (khuyến nghị)
docker compose up -d --build

# Mở http://localhost:18080
```

Tạo tài khoản:

```bash
docker exec catsat_web python manage.py createsuperuser
```

### Chạy không dùng Docker

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

---

## Cấu trúc

```
cat_sat/
  de_xuat_logic.py     # Thuật toán Đề xuất thanh sắt (độc lập)
  de_xuat_views.py     # API endpoints
  optimization_logic.py# Logic MCTĐ (không đụng tới)
cat_laser_roi/         # Module MC Laser (không đụng tới)
api/                   # API public cho ERP tích hợp
iea_project/           # Cấu hình Django
docs/                  # Tài liệu kỹ thuật, báo cáo đối chiếu
```

---

## Triển khai

### Cách 1 — Render.com (nhanh nhất, hợp để demo)

Repo có sẵn [`render.yaml`](render.yaml). Các bước:

1. Vào https://dashboard.render.com/blueprints → **New Blueprint Instance**
2. Chọn repo này → Render đọc `render.yaml` và tự dựng 3 thành phần: web service, PostgreSQL, Redis
3. Bấm **Apply**, chờ build xong (~5-10 phút lần đầu)
4. Tạo tài khoản đăng nhập: vào tab **Shell** của web service, chạy
   `python manage.py createsuperuser`

> **Giới hạn gói miễn phí — đọc trước khi dùng cho việc thật:**
> - App **ngủ sau 15 phút** không ai truy cập, lần vào lại mất khoảng 1 phút khởi động
> - Chỉ **512MB RAM, CPU dùng chung** → phần tính toán tối ưu chậm hơn nhiều lần so với chạy trên máy. BOM nhiều cỡ đoạn nhiều khả năng chạy không nổi.
> - PostgreSQL gói free hết hạn sau một thời gian (Render báo trước qua email)
>
> Dùng để xem giao diện và chạy BOM nhỏ. Việc thật nên dùng gói trả phí hoặc server riêng.

### Cách 2 — Server riêng (VPS)

1. Server đã cài Docker
2. Tạo `.env` từ `.env.example`, điền `SECRET_KEY`, `ALLOWED_HOSTS`, mật khẩu CSDL
3. `docker compose -f docker-compose.prod.yml up -d --build`

### Biến môi trường đáng chú ý

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `SOLVER_WORKERS` | `8` | Số luồng bộ giải. Máy chủ CPU dùng chung nên đặt `2` — nhiều luồng tranh nhau còn chậm hơn. |
| `REDIS_URL` | — | Dùng khi dịch vụ cấp Redis dạng URL (Render). Nếu trống thì dùng `REDIS_HOST`. |
| `PORT` | `8000` | Cổng web. Render cấp động, local để trống. |

**Lưu ý bảo mật:** không commit file `.env`. Các script `create_user.py`, `setup_otp.py` yêu cầu truyền mật khẩu qua biến môi trường, không ghi cứng trong code.

---

## Ghi công

Hệ thống gốc: **Duy-Vuong Tran** — [GitHub](https://github.com/vuongcris4)
Module Đề xuất thanh sắt và API tích hợp: **Trịnh Xuân Sang**
