"""
API views cho hệ thống tích hợp ERP.
Tất cả endpoint đều trả JSON, không giữ state.
"""
import hmac
import json
import re
from functools import wraps

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt

from cat_sat.de_xuat_logic import list_material_groups, optimize_one_material


def require_api_key(view_func):
    """
    Chặn request không có header `Authorization: Bearer <ERP_API_KEY>` đúng. Fail-closed:
    ERP_API_KEY rỗng/chưa cấu hình -> từ chối luôn (không phải mở public khi quên set env).
    Dùng hmac.compare_digest để tránh timing attack khi so sánh key.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        expected = settings.ERP_API_KEY
        auth_header = request.headers.get('Authorization', '')
        provided = auth_header[len('Bearer '):] if auth_header.startswith('Bearer ') else ''
        if not expected or not hmac.compare_digest(provided, expected):
            return JsonResponse(
                {"status": "error", "code": "UNAUTHORIZED", "message": "Thiếu hoặc sai API key"},
                status=401,
            )
        return view_func(request, *args, **kwargs)
    return wrapper


def _to_float(v, default=0.0):
    """Ép về float, chịu được chuỗi '2.5', số, hoặc rỗng."""
    try:
        return float(v)
    except (ValueError, TypeError):
        return float(default)


def _to_int(v, default=0):
    """Ép về int qua float (chịu được '2.5', '4.0', số...)."""
    return int(round(_to_float(v, default)))


def _normalize_material_key(k):
    """Chuẩn hoá khoá vật tư giống HỆT cách de_xuat_logic.explode_bom() dựng `material` trong
    group key (gộp khoảng trắng thừa) - PHẢI đồng bộ để khoá trong
    max_waste_percentage_by_material khớp đúng group["material"] mà vòng lặp dưới so sánh."""
    return re.sub(r"\s+", " ", str(k or "")).strip()


def _parse_max_waste_pct_by_material(raw):
    """
    Sanitize `max_waste_percentage_by_material` từ request: chỉ giữ lại entry hợp lệ.

    KHÔNG fuzzy/prefix match khoá không khớp - khớp nhầm lặng lẽ tệ hơn nhiều so với bỏ qua
    và rơi về ngưỡng mặc định (max_waste_percentage) một cách có ghi chép (xem
    resolved_max_waste_pct_by_group trong response - đó là chỗ duy nhất caller cần nhìn vào
    để biết ngưỡng nào THỰC SỰ được áp, không nên đoán qua request đã gửi).
    """
    if not isinstance(raw, dict):
        return {}
    out = {}
    for k, v in raw.items():
        try:
            pct = float(v)
        except (TypeError, ValueError):
            continue
        if not (0 < pct <= 100):
            continue
        key = _normalize_material_key(k)
        if key:
            out[key] = pct
    return out


def _parse_stock_lengths_by_material(raw):
    """
    Sanitize `stock_lengths_by_material` từ request: materialId -> danh sách chiều dài cây (mm).

    Nhận cùng 3 dạng như `stock_lengths` toàn cục cho đỡ phải nhớ 2 luật: số đơn (5850),
    list ([5850, 6000]), hoặc chuỗi cách nhau bởi khoảng trắng/dấu phẩy ("5850 6000").

    Giống `_parse_max_waste_pct_by_material`: KHÔNG fuzzy/prefix match khoá, entry sai định dạng
    thì BỎ QUA và loại sắt đó rơi về `stock_lengths` chung - xem resolved_stock_lengths_by_group
    trong input_echo để biết danh sách nào THỰC SỰ được áp cho từng loại.
    """
    if not isinstance(raw, dict):
        return {}
    out = {}
    for k, v in raw.items():
        parts = [str(x) for x in v] if isinstance(v, (list, tuple)) else str(v).replace(",", " ").split()
        lengths = sorted({_to_float(x) for x in parts if str(x).strip()})
        lengths = [L for L in lengths if L > 0]
        if not lengths:
            continue
        key = _normalize_material_key(k)
        if key:
            out[key] = lengths
    return out


@csrf_exempt  # API không dùng session Django → bỏ CSRF check
@require_http_methods(["POST"])
@require_api_key
def api_de_xuat_propose(request):
    """
    POST /api/v1/de_xuat/propose

    Bung BOM định mức → tối ưu chiều dài mua + số cây mỗi loại sắt.

    Request body (JSON):
    {
      "num_sets": 500,
      "bom": [
        {"part":"chân bàn", "qty_per_set":4, "material":"sắt vuông", "spec":"50×50",
         "cut_length":660.0, "qty_per_part":1},
        ...
      ],
      "stock_lengths": [5850, 6000],   // chỉ những chiều dài THỰC SỰ mua được
      "trim_start": 10,
      "blade_width": 1.0,
      "max_waste_percentage": 1.0,   // ngưỡng MẶC ĐỊNH, áp cho mọi loại sắt không có ngưỡng riêng
      // Ngưỡng RIÊNG cho từng loại sắt, ghi đè max_waste_percentage ở trên. KHOÁ phải khớp
      // ĐÚNG giá trị `material` mà client gửi trong bom[] (sau khi gộp khoảng trắng thừa);
      // khi client gửi spec rỗng thì khoá chính là chuỗi `material` đó. Khoá không khớp loại
      // nào -> BỎ QUA lặng lẽ và dùng ngưỡng mặc định (xem resolved_max_waste_pct_by_group
      // trong input_echo để biết ngưỡng nào THỰC SỰ được áp cho từng loại).
      // Giá trị phải là số trong khoảng (0, 100]; ngoài khoảng đó bị bỏ qua.
      "max_waste_percentage_by_material": {"200": 2.0, "300": 0.8},
      // Chiều dài cây RIÊNG cho từng loại sắt, ghi đè "stock_lengths" ở trên. Khoá khớp cùng
      // cách như max_waste_percentage_by_material. Nhận số đơn / list / chuỗi. Khoá không khớp
      // loại nào -> BỎ QUA lặng lẽ, loại đó dùng stock_lengths chung (xem
      // resolved_stock_lengths_by_group trong input_echo để biết danh sách THỰC SỰ áp).
      "stock_lengths_by_material": {"200": [5850], "300": "5850 6000"},
      "max_surplus": 10,
      "auto_scan": false,        // bật vét cạn dải chiều dài (CHẬM: cả trăm lần giải)
      "stop_on_first": false,    // chỉ có tác dụng khi auto_scan=true: dừng ở chiều dài
                                 // ĐẠT ngưỡng đầu tiên thay vì quét hết dải
      "min_length": 4000,        // 3 tham số dưới chỉ dùng khi auto_scan=true
      "max_length": 12000,
      "length_step": 50,
      "time_limit_seconds": 480
    }

    Response: {
      "status": "success" | "error",
      "summary": {...},
      "purchase_plan": [{material, best_stock_length, total_bars, waste_percentage, pieces, cutting_patterns, ...}, ...],
      "input_echo": {...}
    }
    """
    try:
        # ===== Parse request =====
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError) as e:
        return JsonResponse(
            {"status": "error", "code": "INVALID_JSON", "message": f"JSON không hợp lệ: {str(e)}"},
            status=400
        )

    try:
        # ===== Validate & extract input =====
        num_sets = _to_int(body.get("num_sets", 1), 1)
        if num_sets < 1:
            return JsonResponse(
                {"status": "error", "code": "INVALID_INPUT", "message": "num_sets phải ≥ 1"},
                status=400
            )

        # BOM: list các mảnh định mức
        bom = body.get("bom", [])
        if not bom or not isinstance(bom, list):
            return JsonResponse(
                {"status": "error", "code": "INVALID_INPUT", "message": "bom phải là array không rỗng"},
                status=400
            )

        # Parse BOM rows
        bom_rows = []
        for row in bom:
            if not isinstance(row, dict):
                continue
            cut_len = row.get("cut_length")
            material = row.get("material")
            if cut_len in (None, "") or material in (None, ""):
                continue
            try:
                bom_rows.append({
                    "part": str(row.get("part", "")),
                    "qty_per_set": _to_int(row.get("qty_per_set", 1), 1),
                    "material": str(material or "").strip(),
                    "spec": str(row.get("spec", "")).strip(),
                    "cut_length": _to_float(cut_len, 0),
                    "qty_per_part": _to_int(row.get("qty_per_part", 1), 1),
                })
            except (ValueError, TypeError):
                continue

        if not bom_rows:
            return JsonResponse(
                {"status": "error", "code": "INVALID_INPUT", "message": "Định mức rỗng hoặc không hợp lệ"},
                status=400
            )

        # ===== Parse parameters =====
        # Chiều dài thanh cố định
        raw_lengths = str(body.get("stock_lengths", "")).replace(",", " ")
        stock_lengths = sorted({_to_float(x) for x in raw_lengths.split() if x.strip()})
        if not stock_lengths:
            return JsonResponse(
                {"status": "error", "code": "INVALID_INPUT", "message": "stock_lengths không hợp lệ"},
                status=400
            )

        # Auto-scan range
        min_len = max(100, _to_int(body.get("min_length", 4000), 4000))
        max_len = max(min_len, _to_int(body.get("max_length", 12000), 12000))
        step = max(1, _to_int(body.get("length_step", 50), 50))

        # Parameters
        # Giữ số thập phân: de_xuat_logic đã scale ×10 nội bộ (giống MC Laser) nên
        # không cần ép kerf/trim về int nữa.
        trim_start = max(0.0, _to_float(body.get("trim_start", 10), 10))
        blade_width = max(0.0, _to_float(body.get("blade_width", 1.0), 1.0))
        max_waste_pct = _to_float(body.get("max_waste_percentage", 1.0), 1.0)
        # Ngưỡng RIÊNG theo từng loại sắt (materialId -> %), ghi đè max_waste_pct cho đúng
        # loại đó - xem docstring endpoint. Rỗng nếu client không gửi hoặc gửi sai định dạng.
        max_waste_pct_by_material = _parse_max_waste_pct_by_material(
            body.get("max_waste_percentage_by_material")
        )
        # Chiều dài cây RIÊNG theo từng loại sắt (materialId -> [mm]), ghi đè stock_lengths cho
        # đúng loại đó - xem docstring endpoint. Rỗng nếu client không gửi hoặc gửi sai định dạng.
        stock_lengths_by_material = _parse_stock_lengths_by_material(
            body.get("stock_lengths_by_material")
        )
        max_surplus = max(0, _to_int(body.get("max_surplus", 10), 10))
        # Vét cạn dải chiều dài: TẮT mặc định (tốn thời gian nhất). stop_on_first chỉ
        # có tác dụng khi auto_scan bật.
        auto_scan = bool(body.get("auto_scan", False))
        stop_on_first = bool(body.get("stop_on_first", False))
        time_limit_sec = max(5.0, _to_float(body.get("time_limit_seconds", 480), 480))

        # ===== Call logic =====
        # Bước 1: bung BOM -> danh sách loại sắt (gom theo quy cách) + nhu cầu mỗi cỡ
        material_groups = list_material_groups(bom_rows, num_sets)
        if not material_groups:
            return JsonResponse(
                {"status": "error", "code": "INVALID_INPUT", "message": "Không tách được loại sắt nào từ BOM"},
                status=400
            )

        # Bước 2: với MỖI loại sắt, cắt TRỘN tất cả cỡ trên CÙNG 1 chiều dài tối ưu
        # (đúng thuật toán production đang chạy trên UI de_xuat_index.html)
        results = []
        resolved_max_waste_pct_by_group = {}
        resolved_stock_lengths_by_group = {}
        for group in material_groups:
            # Khoá group["material"] chính là chuỗi `material` client gửi trong bom[] (đã qua
            # cùng phép chuẩn hoá whitespace) - so khớp trực tiếp với khoá đã sanitize ở trên.
            group_max_waste_pct = max_waste_pct_by_material.get(
                _normalize_material_key(group["material"]), max_waste_pct
            )
            resolved_max_waste_pct_by_group[group["material"]] = group_max_waste_pct
            # optimize_one_material() vốn đã nhận stock_lengths THEO TỪNG LỜI GỌI (bên trong còn
            # "for L in sorted(set(stock_lengths))" để chọn cây tốt nhất) - nên chiều dài riêng
            # theo quy cách chỉ là nối dây ở đây, KHÔNG sửa thuật toán.
            group_stock_lengths = stock_lengths_by_material.get(
                _normalize_material_key(group["material"]), stock_lengths
            )
            resolved_stock_lengths_by_group[group["material"]] = group_stock_lengths
            res = optimize_one_material(
                sizes=group["sizes"],
                demands=group["demands"],
                stock_lengths=group_stock_lengths,
                trim=trim_start,
                kerf=blade_width,
                max_waste_pct=group_max_waste_pct,
                min_len=min_len,
                max_len=max_len,
                step=step,
                time_limit_sec=time_limit_sec,
                max_surplus=max_surplus,
                auto_scan=auto_scan,
                stop_on_first=stop_on_first,
            )
            res["material"] = group["material"]  # optimize_one_material không tự gắn tên loại
            results.append(res)

        # ===== Build response =====
        # Tính tổng hợp
        total_bars_all = 0
        total_purchased_mm = 0
        total_waste_mm = 0
        total_surplus_pieces = 0
        any_over_threshold = False

        purchase_plan = []
        for res in results:
            if not res.get("feasible"):
                purchase_plan.append({
                    "material": res.get("material", ""),
                    "feasible": False,
                    # timed_out phân biệt "hết giờ, chưa kết luận được" với "vô nghiệm thật":
                    # client KHÔNG được coi hai ca này như nhau.
                    "timed_out": bool(res.get("timed_out")),
                    # Có giá trị khi loại sắt cắt được nhưng VƯỢT ngưỡng: {length, waste_pct, bars}
                    # -> client biết nên nâng max_waste_percentage lên bao nhiêu.
                    "best_achievable": res.get("best_achievable"),
                    "reason": res.get("reason", ""),
                    # Ngưỡng THỰC SỰ đã dùng cho loại này (riêng hoặc mặc định) - thiếu field
                    # này thì client không biết phải nới đúng ngưỡng nào khi báo vô nghiệm.
                    "max_waste_pct_threshold": resolved_max_waste_pct_by_group.get(
                        res.get("material", "")
                    ),
                })
                continue

            # Chuẩn bị response cho 1 loại sắt
            item = {
                "material": res.get("material", ""),
                "feasible": True,
                "best_stock_length": res.get("best_length"),
                "length_source": res.get("source", "fixed"),
                "total_bars": res.get("total_bars", 0),
                "total_purchased_mm": res.get("total_purchased_mm", 0),
                "total_waste_mm": res.get("total_waste_mm", 0),
                "waste_percentage": round(res.get("waste_pct", 0), 4),
                "total_surplus_pieces": res.get("total_surplus_pieces", 0),
                # Khúc sắt còn NGUYÊN (chưa cắt) từ cây cuối -> nhập kho, cắt được cỡ
                # bất kỳ. KHÔNG phải phế liệu, cũng không phải đoạn dư đã cắt.
                "mau_nguyen_mm": res.get("mau_nguyen_mm", 0),
                "over_threshold": res.get("over_waste", False),
                "max_waste_pct_threshold": res.get("max_waste_pct", max_waste_pct),
                # > 0 nghĩa là còn chiều dài chưa chấm xong -> phương án CHƯA chắc tối ưu.
                "timeout_count": res.get("timeout_count", 0),
                "timeout_lengths": res.get("timeout_lengths", []),
            }

            # Chi tiết cỡ đoạn (demand vs produced)
            pieces = []
            cut_lengths = res.get("cut_lengths", [])
            demands = res.get("demands", [])
            produced = res.get("produced", [])
            for i, cl in enumerate(cut_lengths):
                pieces.append({
                    "size": cl,
                    "demand": demands[i] if i < len(demands) else 0,
                    "produced": produced[i] if i < len(produced) else 0,
                    "surplus": (produced[i] - demands[i]) if i < len(produced) else 0,
                })
            item["pieces"] = pieces

            # Kế hoạch cắt (cutting patterns)
            cutting_patterns = []
            for p_idx, plan_row in enumerate(res.get("plan", [])):
                pattern = {
                    "pattern_id": p_idx + 1,
                    "stock_length": plan_row.get("stock_length", 0),
                    "counts": list(plan_row.get("counts", [])),
                    "bars": plan_row.get("bars", 0),
                    "waste_per_bar": plan_row.get("waste_per_bar", 0),
                    # > 0 nghĩa là cây này CẮT DỞ: dừng sớm, phần còn lại để nguyên.
                    "mau_nguyen_mm": plan_row.get("mau_nguyen_mm", 0),
                    "pieces_breakdown": [
                        {"size": cut_lengths[j], "count": plan_row.get("counts", [])[j]}
                        for j in range(len(cut_lengths))
                        if j < len(plan_row.get("counts", []))
                    ]
                }
                cutting_patterns.append(pattern)
            item["cutting_patterns"] = cutting_patterns

            # So sánh chiều dài cố định
            fixed_evals = []
            for fe in res.get("fixed_evals", []):
                fixed_evals.append({
                    "length": fe.get("length", 0),
                    "bars": fe.get("bars", 0),
                    "waste_pct": round(fe.get("waste_pct", 0), 4)
                })
            item["length_comparison"] = fixed_evals

            # Tối ưu bất kỳ (scan)
            scan_opt = res.get("scan_optimal")
            item["optimal_custom_length"] = scan_opt.get("length") if scan_opt else None

            purchase_plan.append(item)

            # Cộng dồn tổng
            total_bars_all += item["total_bars"]
            total_purchased_mm += item["total_purchased_mm"]
            total_waste_mm += item["total_waste_mm"]
            total_surplus_pieces += item["total_surplus_pieces"]
            if item.get("over_threshold"):
                any_over_threshold = True

        # Tổng hợp
        summary = {
            "num_sets": num_sets,
            "num_material_groups": len([r for r in results if r.get("feasible")]),
            "total_bars_all": total_bars_all,
            "total_purchased_mm": total_purchased_mm,
            "total_waste_mm": total_waste_mm,
            "total_surplus_pieces": total_surplus_pieces,
            "waste_percentage": round(
                (total_waste_mm / total_purchased_mm * 100) if total_purchased_mm else 0,
                4
            ),
            "any_over_threshold": any_over_threshold,
        }

        return JsonResponse({
            "status": "success",
            "summary": summary,
            "purchase_plan": purchase_plan,
            "input_echo": {
                "num_sets": num_sets,
                "stock_lengths": stock_lengths,
                "trim_start": trim_start,
                "blade_width": blade_width,
                "max_waste_percentage": max_waste_pct,
                # Dict thô client gửi (đã sanitize) + ngưỡng THỰC SỰ áp cho từng loại sau khi
                # so khớp - nếu khoá client gửi không khớp loại nào, dict dưới sẽ toàn giá trị
                # mặc định dù dict trên không rỗng, đó là dấu hiệu key sai chứ không phải tính
                # năng không hoạt động.
                "max_waste_percentage_by_material": max_waste_pct_by_material,
                "resolved_max_waste_pct_by_group": resolved_max_waste_pct_by_group,
                "stock_lengths_by_material": stock_lengths_by_material,
                "resolved_stock_lengths_by_group": resolved_stock_lengths_by_group,
                "max_surplus": max_surplus,
                "min_length": min_len,
                "max_length": max_len,
                "length_step": step,
                "auto_scan": auto_scan,
                "stop_on_first": stop_on_first,
            }
        }, status=200)

    except Exception as e:
        error_body = {
            "status": "error",
            "code": "SOLVER_ERROR",
            "message": str(e),
        }
        if settings.DEBUG:
            import traceback
            error_body["traceback"] = traceback.format_exc()
        return JsonResponse(error_body, status=500)
