"""
View màn "Đề xuất thanh sắt" — ĐỘC LẬP với MCTĐ và MC Laser.
Tính TUẦN TỰ từng loại sắt: mỗi loại -> 1 chiều dài tối ưu (cắt trộn tất cả cỡ) + đề xuất mua.
"""

import json
from django.shortcuts import render
from django.http import JsonResponse

from .de_xuat_logic import list_material_groups, optimize_one_material


def _to_float(v, default=0.0):
    """Ép về float, chịu được chuỗi '2.5', số, hoặc rỗng."""
    try:
        return float(v)
    except (ValueError, TypeError):
        return float(default)


def _to_int(v, default=0):
    """Ép về int qua float (chịu được '2.5', '4.0', số...)."""
    return int(round(_to_float(v, default)))


# ==========================================================================
# MOCK DEMO — sẽ BỎ khi lên ERP thật.
# Trong production: cat_sat_iea KHÔNG giữ danh mục sản phẩm/định mức.
# ERP BE mới là bên lưu sản phẩm + định mức và gửi BOM sang API tính.
# Danh mục dưới đây chỉ để test workflow tại localhost (đóng vai ERP tạm thời).
# Mỗi phần tử: {"id", "name", "bom": [[Tên mảnh, SL/bộ, Nguyên liệu, Quy cách, Dài cắt, SL/mảnh], ...]}
# ==========================================================================
PRODUCT_CATALOG = [
    {
        "id": "j55",
        "name": "Bàn J55 (Meiying 8)",
        "bom": [
            ["chân bàn", 4, "sắt vuông", "50*50", 660, 1],
            ["chân bàn", 4, "sắt hộp", "25*50", 200, 1],
            ["đoạn dài", 2, "sắt hộp", "25*50", 930, 1],
            ["đoạn ngắn", 2, "sắt hộp", "25*50", 765, 1],
            ["giằng bàn", 1, "sắt vuông", "20*20", 840, 1],
            ["viền bàn", 2, "sắt hộp", "25*50", 695, 1],
        ],
    },
    {
        "id": "ban_don",
        "name": "Bàn đơn 1m2 (demo)",
        "bom": [
            ["chân bàn", 4, "sắt vuông", "50*50", 720, 1],
            ["khung dài", 2, "sắt hộp", "25*50", 1150, 1],
            ["khung ngắn", 2, "sắt hộp", "25*50", 550, 1],
            ["giằng", 2, "sắt vuông", "20*20", 500, 1],
        ],
    },
    {
        "id": "ghe_tinh_yeu",
        "name": "Ghế tình yêu (860×510×1225)",
        "bom": [
            ["chân ghế", 2, "sắt vuông", "12x12", 520, 1],
            ["chân ghế", 2, "sắt hộp", "10x20", 488, 1],
            ["chân ghế", 2, "sắt vuông", "12x12", 510, 1],
            ["chân ghế", 2, "sắt Fi", "Ø21", 612, 1],
            ["chân ghế", 2, "sắt Fi", "Ø21", 590.5, 1],
            ["bàn trà", 1, "sắt hộp", "10x20", 305, 2],
            ["bàn trà", 1, "sắt vuông", "20x20", 490, 2],
            ["bàn trà", 1, "sắt hộp", "10x20", 305, 2],
            ["bàn trà", 1, "sắt vuông", "20x20", 160, 2],
            ["hông trước", 2, "sắt hộp", "10x20", 483, 1],
            ["hông trước", 2, "sắt hộp", "10x20", 200, 1],
            ["hông trước", 2, "sắt vuông", "20x20", 483, 1],
            ["hông trước", 2, "sắt vuông", "20x20", 200, 1],
            ["hông bên", 2, "sắt hộp", "10x20", 428, 1],
            ["hông bên", 2, "sắt vuông", "20x20", 200, 1],
            ["hông bên", 2, "sắt vuông", "20x20", 428, 1],
            ["hông bên", 2, "sắt hộp", "10x20", 200, 1],
            ["mê ghế", 2, "sắt vuông", "20x20", 460, 2],
            ["mê ghế", 2, "sắt hộp", "10x20", 420, 2],
            ["mơ giữa", 1, "sắt vuông", "20x20", 460, 2],
            ["mơ giữa", 1, "sắt vuông", "20x20", 310, 2],
            ["tựa lớn", 2, "sắt Fi", "Ø21", 500, 1],
            ["tựa lớn", 2, "sắt hộp", "10x20", 527, 1],
            ["tựa lớn", 2, "sắt vuông", "15x15", 460, 1],
            ["tựa lớn", 2, "sắt hộp", "10x20", 452.7, 1],
            ["tựa lớn", 2, "sắt Fi", "Ø21", 255, 1],
            ["tựa nhỏ", 1, "sắt vuông", "20x20", 295, 1],
            ["tựa nhỏ", 1, "sắt hộp", "10x20", 420, 2],
            ["tựa nhỏ", 1, "sắt vuông", "15x15", 295, 1],
            ["tựa nhỏ", 1, "sắt vuông", "20x20", 275, 1],
            ["mơ dưới", 1, "sắt vuông", "20x20", 265, 2],
            ["mơ dưới", 1, "sắt hộp", "10x20", 460, 1],
            ["mơ dưới", 1, "sắt vuông", "12x12", 265, 1],
            ["chân dưới", 2, "sắt Fi", "Ø21", 175, 1],
        ],
    },
]

# Chỉ 2 chiều dài này là MUA ĐƯỢC trên thực tế. Trước đây mặc định còn có 7000/8000
# nên hệ thống đề xuất mua cây 8000mm — một phương án không đặt được hàng.
DEFAULT_STOCK_LENGTHS = "5850 6000"


def _parse_bom(rows):
    bom_rows = []
    for row in rows or []:
        if not row or len(row) < 6:
            continue
        part, qty_set, material, spec, cut_len, qty_part = row[:6]
        if cut_len in (None, "") or material in (None, ""):
            continue
        try:
            bom_rows.append({
                "part": str(part or ""),
                "qty_per_set": _to_int(qty_set, 0),
                "material": str(material or "").strip(),
                "spec": str(spec or "").strip(),
                "cut_length": _to_float(cut_len, 0),
                "qty_per_part": _to_int(qty_part, 1),
            })
        except (ValueError, TypeError):
            continue
    return bom_rows


def _parse_params(data):
    raw = str(data.get("stock_lengths", ""))
    stock_lengths = sorted({_to_float(x) for x in raw.replace(",", " ").split() if x.strip()})
    min_len = max(100, _to_int(data.get("min_len", 4000)))
    max_len = max(min_len, _to_int(data.get("max_len", 12000)))
    return {
        # Giữ số thập phân: solver đã scale ×10 nội bộ nên không cần ép về int nữa.
        "trim": max(0.0, _to_float(data.get("trim", 0))),
        # MC Laser KHÔNG có ô lưỡi cắt -> hardcode kerf = 1mm (giống MC Laser)
        "kerf": max(0.0, _to_float(data.get("kerf", 1), 1)),
        "max_waste_pct": _to_float(data.get("max_waste_pct", 1.0), 1.0),
        "max_surplus": max(0, _to_int(data.get("max_surplus", 10))),  # cho phép dư tối đa mỗi cỡ
        "min_len": min_len,
        "max_len": max_len,
        "step": max(1, _to_int(data.get("step", 50))),
        "stock_lengths": stock_lengths,
        # Nút bật/tắt vét cạn chiều dài (giống MC Laser) — mặc định TẮT vì đây là
        # phần tốn thời gian nhất, không nên tự chạy ngầm.
        "auto_scan": bool(data.get("auto_scan", False)),
        "stop_on_first": bool(data.get("stop_on_first", False)),
        # Thời gian chạy tối đa (phút) -> giây cho mỗi lần giải solver
        "time_limit_sec": max(5.0, _to_float(data.get("time_limit_minutes", 2), 2) * 60.0),
    }


def de_xuat_index(request):
    context = {
        # MOCK: danh mục sản phẩm để chọn (thật ra sẽ do ERP cấp). Bảng khởi tạo TRỐNG.
        "product_catalog": json.dumps(PRODUCT_CATALOG),
        "default_stock_lengths": DEFAULT_STOCK_LENGTHS,
        "default_num_sets": 50,
        "default_trim": 0,
    }
    return render(request, "cat_sat/de_xuat_index.html", context)


def de_xuat_materials(request):
    """Bước 1: từ định mức -> danh sách các loại sắt (gom theo quy cách) để chạy tuần tự."""
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Chỉ hỗ trợ POST."}, status=400)
    try:
        data = json.loads(request.body)
        num_sets = max(1, _to_int(data.get("num_sets", 1), 1))
        bom_rows = _parse_bom(data.get("bom", []))
        if not bom_rows:
            return JsonResponse({"status": "error", "message": "Định mức rỗng hoặc không hợp lệ."}, status=400)
        groups = list_material_groups(bom_rows, num_sets)
        return JsonResponse({"status": "success", "num_sets": num_sets, "materials": groups})
    except Exception as e:
        return JsonResponse({"status": "error", "message": f"Lỗi: {e}"}, status=500)


def de_xuat_optimize_material(request):
    """Bước 2: tính đề xuất cho MỘT loại sắt (frontend gọi lần lượt từng loại)."""
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Chỉ hỗ trợ POST."}, status=400)
    try:
        data = json.loads(request.body)
        sizes = [_to_float(x) for x in data.get("sizes", [])]   # giữ số thập phân
        demands = [_to_int(x) for x in data.get("demands", [])]
        if not sizes or len(sizes) != len(demands):
            return JsonResponse({"status": "error", "message": "Dữ liệu cỡ/nhu cầu không hợp lệ."}, status=400)

        p = _parse_params(data)
        if not p["stock_lengths"]:
            return JsonResponse({"status": "error", "message": "Chưa nhập chiều dài thanh sắt cố định."}, status=400)

        res = optimize_one_material(
            sizes, demands, p["stock_lengths"], p["trim"], p["kerf"],
            p["max_waste_pct"], p["min_len"], p["max_len"], p["step"],
            time_limit_sec=p["time_limit_sec"], max_surplus=p["max_surplus"],
            auto_scan=p["auto_scan"], stop_on_first=p["stop_on_first"],
        )
        return JsonResponse({"status": "success", "material": data.get("material", ""), "result": res})
    except Exception as e:
        return JsonResponse({"status": "error", "message": f"Lỗi: {e}"}, status=500)
