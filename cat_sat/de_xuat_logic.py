"""
Logic cho màn "Đề xuất thanh sắt" — HOÀN TOÀN ĐỘC LẬP với MCTĐ và MC Laser.

Không import gì từ cat_sat/optimization_logic.py hay cat_laser_roi.
Có dùng OR-Tools CP-SAT (đã là dependency sẵn của dự án) nhưng model viết riêng ở đây,
không đụng tới pipeline/pattern-cache của 2 module kia.

Bài toán 2 tầng:
  Tầng 1 (BOM explosion): định mức sản phẩm -> nhu cầu cắt theo (nguyên liệu, chiều dài đoạn).
  Tầng 2 (multi-length cutting stock): với mỗi nguyên liệu, chọn mua mỗi chiều dài thanh
         bao nhiêu cây để TỔNG SẮT MUA ít nhất (được trộn nhiều chiều dài).

CÔNG THỨC ĐÃ ĐỒNG BỘ với MC Laser (cat_laser_roi/optimization_logic.py):
  - SCALING_FACTOR = 10: mọi phép tính chạy trên số nguyên đã nhân 10 -> giữ được
    1 chữ số thập phân (đoạn 660.5mm, lưỡi cắt 1.2mm... không còn bị làm tròn).
  - Liệt kê pattern giới hạn theo SỐ LƯỢNG, KHÔNG theo thời gian.
  - Lọc pattern theo TỔNG SẮT DÙNG (đoạn + lưỡi cắt) — khớp với công thức hao hụt.
  - Tối ưu 2 tầng từ điển: min hao hụt -> khoá cứng kết quả -> min tồn kho.

HAI CHỖ CỐ Ý KHÁC MC Laser (xem ghi chú tại chỗ để biết lý do):
  1. Cận trên số đoạn/cây bám nhu cầu thật, không chặn cứng 30 đoạn.
  2. Ràng buộc tồn kho KHÔNG cho phép giao thiếu (MC Laser cho thiếu tới −max_surplus).
"""

import math
import os
import re
from collections import defaultdict

from ortools.sat.python import cp_model

# Hệ số nhân để biến giá trị thập phân thành số nguyên cho CP-SAT (giống MC Laser).
SCALING_FACTOR = 10
# Trần số pattern liệt kê cho mỗi chiều dài thanh (giống MC Laser).
SOLUTION_LIMIT = 100000

# Số CỠ ĐOẠN KHÁC NHAU tối đa được phép cắt trên cùng một cây.
# Số pattern nhân ~5 lần mỗi khi thêm một cỡ đoạn (đo thực tế: 4 cỡ→60, 5→423,
# 6→2.239, 10→13.000+), nên nhóm 9-10 cỡ mất hàng chục phút nếu không giới hạn.
# Giới hạn 4 đổi IP từ 60-95s (cap≥5/không giới hạn) xuống 3-14s.
#
# ĐÂY LÀ XẤP XỈ, KHÔNG PHẢI NGHIỆM CHÍNH XÁC: đo trên 1 BOM cụ thể (ghế 20x20)
# cap=4 trùng khớp cap=None, nhưng đo thêm trên 3 bộ dữ liệu 9 cỡ ngẫu nhiên thì
# cap=4 lệch so với nghiệm tối ưu thật (đã CHỨNG MINH bằng trạng thái OPTIMAL của
# solver, không phải do hết giờ): sai lệch hao hụt ~0.001-0.0014 điểm %, chênh
# 1-3 cây trên tổng 1300-1600 cây (~0.1-0.2%). cap≥5 KHÔNG bù lại được bằng tốc độ
# (60-95s, ngang cap=None) nên không phải lựa chọn trung gian tốt — chỉ có 2 lựa
# chọn thực tế: cap≤4 (nhanh, sai số nhỏ) hoặc cap=None (chậm, chính xác).
# Chấp nhận đánh đổi này vì sai số quá nhỏ so với lợi ích tốc độ 5-10 lần.
#
# Ngoài ra một cây phải cắt ra 10 kích thước khác nhau cũng rất khó thực thi ở xưởng.
# Nếu giới hạn làm mất nghiệm hoàn toàn (patterns rỗng), optimize_material tự động
# sinh lại KHÔNG giới hạn — lưới an toàn này chỉ bắt được ca rỗng, không bắt được
# ca "có nghiệm nhưng không phải nghiệm tốt nhất" như mô tả ở trên.
MAX_SIZES_PER_BAR = 4

# Ngân sách thời gian riêng cho khâu LIỆT KÊ pattern (tách khỏi thời gian giải IP).
# Liệt kê thêm gần như không cải thiện nghiệm, nên không đáng để nó ăn cả phút.
ENUM_TIME_LIMIT = 30.0

# Số luồng cho bộ giải. Mặc định 8 (hợp với máy/server nhiều nhân), nhưng trên máy chủ
# CPU dùng chung (vd gói free của PaaS) thì 8 luồng tranh nhau còn CHẬM hơn ít luồng —
# đặt biến môi trường SOLVER_WORKERS=2 cho các môi trường đó.
SOLVER_WORKERS = max(1, int(os.environ.get("SOLVER_WORKERS", "8")))


def _scale(v):
    """mm thật -> đơn vị nội bộ (đã nhân SCALING_FACTOR)."""
    return int(round(float(v) * SCALING_FACTOR))


# Các ký hiệu nhân hay gặp trong file định mức, đều quy về 'x'.
# KHÔNG đưa dấu '.' vào đây: quy cách có số thập phân ('0.6', '1.5') sẽ hỏng.
_SEP_CHARS = ("*", "X", "×", "·")
_SEP_RE = re.compile(r"\s*x\s*")


def normalize_spec(spec):
    """
    Chuẩn hoá ký hiệu quy cách về dạng dùng 'x': '10*20', '10X20', '10 × 20' -> '10x20'.

    Quy cách là KHOÁ GOM NHÓM (xem explode_bom): hai cách viết khác nhau của cùng một
    loại sắt sẽ bị tách thành hai nhóm, khiến hệ thống mua hai lô sắt giống hệt nhau và
    hao hụt tăng vô cớ. Định mức thực tế hay viết lẫn '*' với 'x' ngay trong cùng một
    bảng, nên phải quy về một mối tại đây — chỗ duy nhất mọi đường vào đều đi qua.

    Ống tròn ('Ø21') không có dấu nhân nên giữ nguyên.
    """
    s = str(spec or "").strip()
    for ch in _SEP_CHARS:
        s = s.replace(ch, "x")
    s = _SEP_RE.sub("x", s)           # '10 x 20' -> '10x20'
    return re.sub(r"\s+", " ", s)


def _giu_lai_mau_nguyen(plan, cuts_s, produced, demands, trim_s, kerf_s):
    """
    Biến ĐOẠN DƯ ĐÃ CẮT thành MẨU SẮT NGUYÊN chưa cắt.

    Vì sao cần: nhu cầu hiếm khi chia hết cho số đoạn mỗi cây, nên cây cuối luôn cắt
    thừa vài đoạn (vd cần 2.000 đoạn 660mm, mỗi cây 9 đoạn -> mua 223 cây, ra 2.007
    đoạn, DƯ 7). Bảy đoạn đó là sắt tốt nhưng đã bị cắt cứng thành 660mm, chỉ dùng
    được cho đơn nào cần đúng cỡ ấy.

    Thay vì cắt nốt, ta cắt cây cuối ÍT LẠI đúng bằng phần thừa, để lại một khúc dài
    còn nguyên (vd 4.668mm) — khúc này cắt được cỡ bất kỳ. Sắt cắt rồi không nối lại
    được, nên để nguyên là giữ lại quyền lựa chọn cho đơn sau.

    KHÔNG đổi số cây phải mua và KHÔNG đổi số đoạn giao cho khách — chỉ đổi hình dạng
    phần sắt còn lại. Chạy sau khi đã giải xong nên không ảnh hưởng tốc độ.

    Trả về (plan_moi, mau_nguyen_s, bu_tru_phe_lieu_s, produced_moi) — đơn vị đã scale.
    """
    n = len(cuts_s)
    surplus = [produced[k] - demands[k] for k in range(n)]
    if sum(surplus) <= 0 or not plan:
        return plan, 0, 0, produced

    # Chọn cây bỏ được NHIỀU SẮT NHẤT ra khỏi lưỡi cưa -> mẩu nguyên dài nhất.
    best_i, best_bo, best_giam = None, None, -1
    for i, row in enumerate(plan):
        bo = [min(row["counts"][k], surplus[k]) for k in range(n)]
        giam = sum(bo[k] * (cuts_s[k] + kerf_s) for k in range(n))
        if giam > best_giam:
            best_i, best_bo, best_giam = i, bo, giam
    if best_giam <= 0:
        return plan, 0, 0, produced

    row = plan[best_i]
    counts_moi = tuple(row["counts"][k] - best_bo[k] for k in range(n))
    S_s = _scale(row["stock_length"])
    dung = sum(counts_moi[k] * (cuts_s[k] + kerf_s) for k in range(n))
    mau_s = S_s - trim_s - dung                      # khúc còn nguyên, KHÔNG phải phế liệu
    if mau_s <= 0:
        return plan, 0, 0, produced

    # Cây cắt dở giờ chỉ mất phần tề đầu, thay vì cả khúc thừa đuôi như trước.
    bu_tru_s = _scale(row["waste_per_bar"]) - trim_s

    plan_moi = [dict(r) for r in plan]
    plan_moi[best_i]["bars"] -= 1
    if plan_moi[best_i]["bars"] <= 0:
        plan_moi.pop(best_i)
    plan_moi.append({
        "stock_length": row["stock_length"],
        "counts": counts_moi,
        "bars": 1,
        "waste_per_bar": trim_s / SCALING_FACTOR,
        "mau_nguyen_mm": mau_s / SCALING_FACTOR,     # cây này cắt DỞ, để lại mẩu nguyên
    })
    produced_moi = [produced[k] - best_bo[k] for k in range(n)]
    return plan_moi, mau_s, bu_tru_s, produced_moi


def _unsolved(status, time_limit, max_surplus):
    """
    Dựng kết quả thất bại, TÁCH BẠCH "hết giờ" với "thật sự vô nghiệm".

    CP-SAT trả UNKNOWN khi hết thời gian mà chưa tìm được nghiệm nào, INFEASIBLE khi
    chứng minh được là không có nghiệm. Gộp chung hai ca này sẽ âm thầm loại bỏ những
    chiều dài TỐT chỉ vì solver chưa kịp chạy xong, mà người dùng lại đọc thành "chiều
    dài này không dùng được" — sai hoàn toàn về bản chất.
    """
    timed_out = (status == cp_model.UNKNOWN)
    if timed_out:
        reason = (f"Hết {time_limit:.0f}s mà chưa tìm ra nghiệm — CHƯA kết luận được "
                  f"chiều dài này tốt hay xấu. Hãy tăng thời gian chạy.")
    else:
        reason = (f"Không có phương án nào thoả ràng buộc tồn kho "
                  f"(tối đa {max_surplus} đoạn dư mỗi cỡ).")
    return {"feasible": False, "timed_out": timed_out, "reason": reason}


# ===================================================================
# TẦNG 1: Bung định mức (BOM) -> nhu cầu theo nguyên liệu
# ===================================================================
def explode_bom(bom_rows, num_sets):
    """
    bom_rows: list dict {part, qty_per_set, material, spec, cut_length, qty_per_part}
    Trả về: dict { "material spec": { cut_length(float, 1 chữ số thập phân): demand(int) } }
    """
    groups = defaultdict(lambda: defaultdict(int))
    for r in bom_rows:
        # Giữ 1 chữ số thập phân — đúng độ phân giải mà SCALING_FACTOR biểu diễn được.
        cut_len = round(float(r["cut_length"]), 1)
        if cut_len <= 0:
            continue
        demand = int(r["qty_per_set"]) * int(r["qty_per_part"]) * int(num_sets)
        if demand <= 0:
            continue
        # Chuẩn hoá ký hiệu quy cách ('10*20' và '10x20' phải về cùng một nhóm) và gộp
        # khoảng trắng thừa trong tên nguyên liệu, trước khi dựng khoá gom nhóm.
        mat = re.sub(r"\s+", " ", str(r["material"] or "")).strip()
        key = f'{mat} {normalize_spec(r["spec"])}'.strip()
        groups[key][cut_len] += demand
    return {k: dict(v) for k, v in groups.items()}


# ===================================================================
# TẦNG 2a: Sinh các kiểu cắt (pattern) cho 1 chiều dài thanh
# ===================================================================
def generate_patterns(cut_lengths, demands, stock_length, trim, kerf,
                      max_waste_ratio=0.20, max_patterns=SOLUTION_LIMIT,
                      time_limit=ENUM_TIME_LIMIT, max_sizes_per_bar=None):
    """
    Liệt kê các pattern khả thi cho 1 cây có chiều dài stock_length.
    - usable = stock_length - trim
    - mỗi đoạn tốn thêm kerf (hao hụt lưỡi)
    - chỉ giữ pattern có hao hụt <= max_waste_ratio để tránh bùng nổ tổ hợp

    Trả về (rows, complete):
      rows     – list dict { counts, used, waste }, đơn vị đã scale
      complete – True nếu ĐÃ liệt kê hết; False nếu bị chặn bởi thời gian/số lượng.

    Vì sao cần cờ `complete`: số pattern bùng nổ theo số cỡ đoạn (đo thực tế trên cây
    6000mm, lọc 1%: 4 cỡ→60, 5 cỡ→423, 6 cỡ→2.239, mỗi cỡ thêm vào nhân ~5 lần). Với
    9-10 cỡ thì liệt kê hết mất hàng giờ. Nhưng nếu chặn mà KHÔNG báo thì nghiệm trả
    về trông như tối ưu trong khi thực chất chỉ tối ưu trên tập kiểu cắt bị cắt cụt —
    đó là lý do phải trả cờ này lên cho tầng trên nói với người dùng.
    """
    stock_s = _scale(stock_length)
    trim_s = _scale(trim)
    kerf_s = _scale(kerf)
    cuts_s = [_scale(c) for c in cut_lengths]

    usable_s = stock_s - trim_s
    n = len(cuts_s)
    if usable_s <= 0 or n == 0:
        return [], True

    model = cp_model.CpModel()
    xs = []
    for i, cl_s in enumerate(cuts_s):
        # Cận trên bám nhu cầu thật: không cắt quá nhu cầu, không quá sức chứa của cây.
        # MC Laser chặn cứng 30 đoạn/cây; với đoạn ngắn (một cây 6m chứa được cả trăm
        # đoạn) con số đó loại oan pattern hợp lệ, nên CỐ Ý không copy sang đây.
        ub = min(usable_s // max(1, cl_s), int(demands[i]))
        xs.append(model.NewIntVar(0, max(0, ub), f"x{i}"))

    material_pieces = sum(xs[i] * cuts_s[i] for i in range(n))   # sắt thành đoạn hữu ích
    total_used = material_pieces + sum(xs) * kerf_s              # + hao hụt lưỡi
    model.Add(total_used <= usable_s)
    model.Add(sum(xs) >= 1)
    # Prune: loại pattern phí quá nhiều. Dùng ĐÚNG đại lượng của công thức hao hụt bên
    # dưới (đoạn + lưỡi) như MC Laser — bản cũ lọc theo mỗi phần đoạn nên loại nhầm cả
    # những pattern mà hao hụt thật vẫn nằm trong ngưỡng.
    model.Add(total_used >= int(stock_s * (1 - max_waste_ratio)))

    # Giới hạn số CỠ ĐOẠN KHÁC NHAU trên một cây (xem MAX_SIZES_PER_BAR).
    if max_sizes_per_bar is not None and n > max_sizes_per_bar:
        used_flags = []
        for i in range(n):
            b = model.NewBoolVar(f"b{i}")
            model.Add(xs[i] >= 1).OnlyEnforceIf(b)
            model.Add(xs[i] == 0).OnlyEnforceIf(b.Not())
            used_flags.append(b)
        model.Add(sum(used_flags) <= max_sizes_per_bar)

    class _Collector(cp_model.CpSolverSolutionCallback):
        def __init__(self, vars_, limit):
            super().__init__()
            self._vars = vars_
            self._limit = limit
            self.rows = []
            self.hit_limit = False

        def on_solution_callback(self):
            if len(self.rows) >= self._limit:
                self.hit_limit = True
                self.StopSearch()
                return
            counts = tuple(int(self.Value(v)) for v in self._vars)
            used = sum(counts[i] * cuts_s[i] for i in range(n))
            # Hao hụt GIỐNG MC Laser: KHÔNG tính lưỡi cắt (kerf) — coi kerf là "sắt đã dùng".
            # waste = chiều dài cây − đoạn − lưỡi cắt  (= tề đầu + khúc thừa đuôi).
            kerf_loss = sum(counts) * kerf_s
            self.rows.append({"counts": counts, "used": used,
                              "waste": stock_s - used - kerf_loss})

    solver = cp_model.CpSolver()
    solver.parameters.enumerate_all_solutions = True
    solver.parameters.max_time_in_seconds = time_limit
    collector = _Collector(xs, max_patterns)
    status = solver.Solve(model, collector)
    # OPTIMAL/INFEASIBLE = đã duyệt hết không gian tìm kiếm. UNKNOWN = bị thời gian cắt ngang.
    complete = (status in (cp_model.OPTIMAL, cp_model.INFEASIBLE)) and not collector.hit_limit
    return collector.rows, complete


# ===================================================================
# TẦNG 2b: Chọn mua thanh nào, mỗi loại bao nhiêu (minimize hao hụt)
# ===================================================================
def optimize_material(cut_lengths, demands, stock_lengths, trim, kerf,
                      max_waste_ratio=0.20, time_limit=8.0, allow_mix=True,
                      max_surplus=10):
    """
    Với 1 nguyên liệu: sinh pattern cho từng chiều dài thanh, rồi giải IP chọn số thanh
    mỗi (chiều dài, pattern) sao cho hao hụt nhỏ nhất và cắt đủ nhu cầu.

    allow_mix=False: KHÔNG trộn nhiều chiều dài — thử từng chiều dài riêng lẻ rồi chọn
                     chiều dài đơn cho hao hụt thấp nhất (thực tế: mỗi loại chỉ mua 1 chiều dài).
    allow_mix=True : cho phép trộn nhiều chiều dài để ép hao hụt xuống thấp nhất.


    Trả về dict kết quả (xem cuối hàm) hoặc {"feasible": False} nếu không giải được.
    """
    n = len(cut_lengths)

    # Chế độ KHÔNG trộn: đánh giá từng chiều dài đơn, chọn cái tốt nhất
    if not allow_mix and len(stock_lengths) > 1:
        best, best_key = None, None
        for L in stock_lengths:
            r = optimize_material(cut_lengths, demands, [L], trim, kerf,
                                  max_waste_ratio, time_limit, allow_mix=True, max_surplus=max_surplus)
            if not r.get("feasible"):
                continue
            key = (round(r["waste_pct"], 4), r["total_purchased_mm"])
            if best is None or key < best_key:
                best, best_key = r, key
        return best or {"feasible": False,
                        "reason": "Không có chiều dài đơn nào khả thi."}

    # 1) Kiểm tra khả thi cơ bản: đoạn dài nhất phải lọt vào thanh dài nhất
    longest_bar_usable = max(stock_lengths) - trim
    if max(cut_lengths) > longest_bar_usable:
        return {"feasible": False,
                "reason": f"Có đoạn {max(cut_lengths):g}mm dài hơn thanh dùng được {longest_bar_usable:g}mm."}

    # 2) Sinh pattern cho từng chiều dài thanh
    # Sinh pattern với giới hạn số cỡ đoạn/cây trước (nhanh hơn nhiều, nghiệm không đổi).
    # Nếu giới hạn khiến KHÔNG còn kiểu cắt nào, sinh lại không giới hạn để chắc chắn
    # không tự tay làm mất nghiệm — đây là lưới an toàn, hiếm khi phải dùng.
    enum_budget = max(1.0, min(float(time_limit), ENUM_TIME_LIMIT))
    limited_sizes_used = False
    for cap in (MAX_SIZES_PER_BAR, None):
        all_patterns = []  # list (stock_length, stock_length_scaled, counts_tuple, waste_scaled)
        patterns_complete = True
        for S in stock_lengths:
            rows, ok = generate_patterns(cut_lengths, demands, S, trim, kerf,
                                         max_waste_ratio, time_limit=enum_budget,
                                         max_sizes_per_bar=cap)
            patterns_complete = patterns_complete and ok
            S_s = _scale(S)
            for r in rows:
                all_patterns.append((S, S_s, r["counts"], r["waste"]))
        if all_patterns:
            limited_sizes_used = cap is not None
            break

    if not all_patterns:
        # Rỗng vì CHƯA duyệt hết ≠ rỗng vì THẬT SỰ không có cách cắt nào. Ca đầu là
        # "chưa biết", tuyệt đối không được báo thành "không đạt ngưỡng".
        if not patterns_complete:
            return {"feasible": False, "timed_out": True, "patterns_truncated": True,
                    "reason": (f"Hết {time_limit:.0f}s mà chưa liệt kê xong các kiểu cắt "
                               f"({len(cut_lengths)} cỡ đoạn là rất nặng) — CHƯA kết luận được. "
                               f"Hãy tăng thời gian chạy hoặc tách bớt cỡ đoạn.")}
        return {"feasible": False,
                "reason": (f"Không có cách cắt nào ≤ {max_waste_ratio * 100:.1f}% hao hụt/cây "
                           f"với các chiều dài đã cho. Hãy tăng % hoặc bật Tự dò chiều dài.")}

    # 3) IP chọn số thanh mỗi pattern
    model = cp_model.CpModel()
    P = len(all_patterns)

    # Cận trên RIÊNG cho từng kiểu cắt, thay cho cận trên chung sum(demands).
    # Kiểu cắt p chứa counts[k] đoạn cỡ k thì dùng quá (nhu_cầu[k]+max_surplus)//counts[k]
    # cây là chắc chắn vượt trần tồn kho -> vô nghiệm. Nói trước cho solver biết điều đó
    # thay vì để nó tự dò: đo thực tế cận trên chung rộng gấp hàng chục lần cận trên thật
    # (vd 9.000 so với trung bình 161), và chính khoảng thừa đó làm solver không chứng minh
    # nổi tối ưu — ca 10 cỡ chạy 150s vẫn dừng ở FEASIBLE, siết lại thì 14-80s ra OPTIMAL.
    y = []
    for p in range(P):
        counts = all_patterns[p][2]
        caps = [(demands[k] + max_surplus) // counts[k]
                for k in range(n) if counts[k] > 0]
        y.append(model.NewIntVar(0, min(caps) if caps else 0, f"y{p}"))

    # Cận dưới cho TỔNG số cây: mỗi cây dài nhất cũng chỉ cho được (S_max − tề đầu) sắt
    # dùng được, nên số cây không thể ít hơn tổng nhu cầu chia cho ngần ấy. Ràng buộc này
    # đúng với cả khi trộn nhiều chiều dài (dùng chiều dài LỚN NHẤT nên không loại oan
    # nghiệm nào), và giúp solver khỏi mò số cây từ 0 đi lên.
    need_s = sum(demands[k] * (_scale(cut_lengths[k]) + _scale(kerf)) for k in range(n))
    max_usable_s = _scale(max(stock_lengths)) - _scale(trim)
    if max_usable_s > 0:
        model.Add(sum(y) >= -(-need_s // max_usable_s))   # -(-a//b) = ceil(a/b)

    # Ràng buộc tồn kho:  0 ≤ (cắt_ra − nhu_cầu) ≤ max_surplus.
    # Cận dưới 0 nghĩa là KHÔNG BAO GIỜ giao thiếu. MC Laser cho phép thiếu tới
    # −max_surplus (tô đỏ cảnh báo) vì module đó không có khái niệm kho; ở đây CỐ Ý
    # không copy — đề xuất mua sắt mà cắt không đủ hàng thì vô nghĩa.
    closing = []
    for k in range(n):
        produced_k = sum(all_patterns[p][2][k] * y[p] for p in range(P))
        c = model.NewIntVar(0, max_surplus, f"c{k}")
        model.Add(c == produced_k - demands[k])
        closing.append(c)

    total_leftover = sum(all_patterns[p][3] * y[p] for p in range(P))   # [3] = waste (đầu mẩu/cây)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_search_workers = SOLVER_WORKERS

    # Tối ưu 2 TẦNG TỪ ĐIỂN như MC Laser (thay cho hàm mục tiêu gộp trọng số cũ):
    #   Tầng 1: tối thiểu PHẾ LIỆU CẮT (đầu mẩu mỗi cây) — đoạn dư KHÔNG tính là phế.
    #   Tầng 2: khoá cứng kết quả tầng 1, rồi tối thiểu tồn kho cuối kỳ.
    model.Minimize(total_leftover)
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return _unsolved(status, time_limit, max_surplus)
    min_leftover = int(round(solver.ObjectiveValue()))
    model.Add(total_leftover == min_leftover)

    # Tầng 2 luôn còn ít nhất nghiệm của tầng 1 nên chỉ vỡ khi hết giờ.
    model.Minimize(sum(closing))
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return _unsolved(status, time_limit, max_surplus)

    # 4) Tổng hợp kết quả (quy đổi ngược về mm thật)
    plan = []            # từng pattern được dùng
    bars_by_length = defaultdict(int)
    produced = [0] * n
    total_purchased_s = 0
    total_leftover_s = 0
    for p in range(P):
        cnt = int(solver.Value(y[p]))
        if cnt <= 0:
            continue
        S, S_s, counts, waste_s = all_patterns[p]
        bars_by_length[S] += cnt
        total_purchased_s += S_s * cnt
        total_leftover_s += waste_s * cnt
        for k in range(n):
            produced[k] += counts[k] * cnt
        plan.append({
            "stock_length": S,
            "counts": counts,
            "bars": cnt,
            "waste_per_bar": waste_s / SCALING_FACTOR,
        })

    total_used_s = sum(demands[k] * _scale(cut_lengths[k]) for k in range(n))

    # Cây cuối: thay vì cắt nốt mấy đoạn không ai cần, để nguyên khúc dài đem nhập kho.
    cuts_s = [_scale(c) for c in cut_lengths]
    plan, mau_nguyen_s, bu_tru_s, produced = _giu_lai_mau_nguyen(
        plan, cuts_s, produced, demands, _scale(trim), _scale(kerf))
    total_leftover_s -= bu_tru_s

    total_surplus_pieces = int(sum(produced[k] - demands[k] for k in range(n)))
    plan.sort(key=lambda r: (r["stock_length"], -r["bars"]))

    return {
        "feasible": True,
        "cut_lengths": cut_lengths,
        "demands": demands,
        "produced": produced,
        "bars_by_length": dict(sorted(bars_by_length.items())),
        "total_bars": sum(bars_by_length.values()),
        "total_purchased_mm": total_purchased_s / SCALING_FACTOR,
        "total_used_mm": total_used_s / SCALING_FACTOR,
        "total_waste_mm": total_leftover_s / SCALING_FACTOR,   # hao hụt = phế liệu cắt (leftover)
        "total_surplus_pieces": total_surplus_pieces,          # đoạn ĐÃ CẮT còn dư
        # Khúc sắt còn NGUYÊN (chưa cắt) từ cây cuối — nhập kho, cắt được cỡ bất kỳ.
        # Khác hẳn phế liệu (vụn bỏ đi) và đoạn dư (đã cắt cứng một kích thước).
        "mau_nguyen_mm": mau_nguyen_s / SCALING_FACTOR,
        "waste_pct": (total_leftover_s / total_purchased_s * 100) if total_purchased_s else 0,
        "plan": plan,
        # True = chưa liệt kê hết kiểu cắt -> nghiệm này tối ưu trên TẬP BỊ CẮT CỤT,
        # có thể còn phương án tốt hơn chưa được xét.
        "patterns_truncated": not patterns_complete,
        # True = mỗi cây chỉ cắt tối đa MAX_SIZES_PER_BAR cỡ đoạn khác nhau.
        "limited_sizes_per_bar": MAX_SIZES_PER_BAR if limited_sizes_used else None,
    }


# ===================================================================
# TÍNH THEO TỪNG LOẠI SẮT (tuần tự): mỗi loại -> 1 chiều dài tối ưu, cắt TRỘN tất cả cỡ
# ===================================================================
def _best_achievable(sizes, demands, stock_lengths, trim, kerf,
                     time_limit_sec, max_surplus):
    """
    Khi KHÔNG cách cắt nào đạt ngưỡng: nới bộ lọc ra để xem thực tế cắt được tới đâu.

    MC Laser gặp ca này chỉ báo "không tìm thấy pattern nào phù hợp" — nghe như hình
    học bất khả thi, trong khi thật ra chỉ là vượt ngưỡng người dùng đặt. Hàm này lấy
    con số thật để nói cho người dùng biết nên nâng ngưỡng lên bao nhiêu.

    Chỉ chạy trên nhánh THẤT BẠI nên không ảnh hưởng tốc độ đường chính.
    Trả về dict {length, waste_pct, bars} hoặc None nếu thật sự không cắt nổi.
    """
    best = None
    for L in sorted(set(stock_lengths)):
        # ratio = 1.0 -> BỎ HẲN bộ lọc hao hụt. Trước đây để cứng 0.6 nên những loại
        # nhu cầu quá nhỏ so với cây sắt (vd 50 chốt 20mm trên cây 5850mm -> thừa 82%)
        # bị báo nhầm thành "không cắt được", trong khi thật ra cắt được thoải mái.
        r = optimize_material(sizes, demands, [L], trim, kerf,
                              max_waste_ratio=1.0, time_limit=time_limit_sec,
                              max_surplus=max_surplus)
        if r.get("feasible") and (best is None or r["waste_pct"] < best["waste_pct"]):
            best = {"length": L, "waste_pct": r["waste_pct"], "bars": r["total_bars"]}
    return best


def _no_solution(sizes, demands, stock_lengths, trim, kerf, time_limit_sec,
                 max_surplus, max_waste_pct, scanned=False):
    """
    Dựng kết quả "không đạt ngưỡng" KÈM con số thực tế cắt được tới đâu.

    MC Laser gặp ca này chỉ báo "❌ Không tìm thấy pattern nào phù hợp" — người đọc
    tưởng hình học bất khả thi và không biết phải nâng ngưỡng lên bao nhiêu. Ở đây nói
    thẳng: đạt được bao nhiêu %, ở chiều dài nào, mấy cây.
    """
    hint = _best_achievable(sizes, demands, stock_lengths, trim, kerf,
                            time_limit_sec, max_surplus)
    if hint:
        return {
            "feasible": False,
            "best_achievable": hint,
            "reason": (f"Không có cách cắt nào đạt ngưỡng {max_waste_pct:g}% hao hụt. "
                       f"Tốt nhất có thể: {hint['waste_pct']:.2f}% "
                       f"({hint['length']:g}mm × {hint['bars']} cây). "
                       f"Nâng ngưỡng lên ≥ {hint['waste_pct']:.2f}% nếu chấp nhận được, "
                       f"hoặc đổi kích thước đoạn cắt."),
        }
    tail = "" if scanned else " Bật 'Dò chiều dài đặt riêng' để tìm chiều dài khác."
    return {"feasible": False,
            "reason": ("Không chiều dài nào cắt được loại này — có đoạn dài hơn cây sắt, "
                       "hoặc ràng buộc tồn kho quá chặt." + tail)}


def list_material_groups(bom_rows, num_sets):
    """Từ định mức trả về danh sách các loại sắt (gom theo quy cách) để frontend chạy tuần tự."""
    groups = explode_bom(bom_rows, num_sets)
    out = []
    for material, demand_map in groups.items():
        sizes = sorted(demand_map.keys(), reverse=True)
        out.append({
            "material": material,
            "sizes": sizes,
            "demands": [demand_map[s] for s in sizes],
        })
    return out


def optimize_one_material(sizes, demands, stock_lengths, trim, kerf, max_waste_pct,
                          min_len, max_len, step, time_limit_sec=8.0, max_surplus=10,
                          auto_scan=False, stop_on_first=False):
    """
    Cho 1 LOẠI sắt (gồm nhiều cỡ đoạn): cắt TRỘN tất cả cỡ trên cùng 1 chiều dài.
    - Chấm từng chiều dài chuẩn (cố định) người dùng nhập -> chọn cái ít hao hụt nhất.
    - Vét cạn khoảng để gợi ý chiều dài tối ưu tuyệt đối (đặt bất kỳ).
    - Ưu tiên đề xuất chiều dài chuẩn nếu đạt ngưỡng %, nếu không thì lấy chiều dài vét cạn.
    - time_limit_sec: giới hạn thời gian cho mỗi lần giải solver.

    auto_scan:     bật/tắt vét cạn dải [min_len, max_len] (nút bật tắt giống MC Laser).
                   TẮT = chỉ chấm các chiều dài chuẩn, trả kết quả tốt nhất trong số đó
                   dù vượt ngưỡng %. Vét cạn là phần TỐN THỜI GIAN NHẤT (cả trăm lần giải)
                   nên để người dùng chủ động bật, không tự chạy ngầm.
    stop_on_first: khi vét cạn, dừng NGAY ở chiều dài đầu tiên đạt ngưỡng % thay vì quét
                   hết dải. Nhanh hơn nhiều nhưng chiều dài tìm được chỉ là "đạt yêu cầu",
                   KHÔNG phải tốt nhất trong dải.
    """
    threshold = max_waste_pct
    # Ngưỡng hao hụt là BỘ LỌC CỨNG ngay khâu sinh pattern (giống MC Laser): kiểu cắt nào
    # phí quá ngưỡng thì KHÔNG BAO GIỜ được sinh ra, nên mọi phương án trả về đều đạt
    # ngưỡng. Đổi lại, loại sắt không đạt sẽ không có nghiệm — nhánh thất bại bên dưới
    # gọi _best_achievable() để nói rõ thực tế cắt được tới đâu.
    strict_ratio = max(0.0, float(max_waste_pct) / 100.0)

    # Đếm số chiều dài phải bỏ qua vì HẾT GIỜ (khác hẳn với vô nghiệm thật) để báo lên UI:
    # nếu con số này > 0 thì kết quả "tốt nhất" bên dưới chưa chắc là tốt nhất.
    timeouts = []
    scan_stopped_early = False

    # 1) Chấm từng chiều dài chuẩn (cắt trộn tất cả cỡ)
    fixed_evals = []
    for L in sorted(set(stock_lengths)):
        r = optimize_material(sizes, demands, [L], trim, kerf,
                              max_waste_ratio=strict_ratio, time_limit=time_limit_sec,
                              max_surplus=max_surplus)
        if r.get("feasible"):
            fixed_evals.append({"length": L, "bars": r["total_bars"],
                                "waste_pct": r["waste_pct"], "result": r})
        elif r.get("timed_out"):
            timeouts.append(L)
    fixed_evals.sort(key=lambda e: e["waste_pct"])
    best_fixed = fixed_evals[0] if fixed_evals else None

    # 2) Nếu CHUẨN đã đạt ngưỡng -> dùng luôn, KHỎI vét cạn nặng (nhanh).
    #    Chỉ vét cạn khi không chiều dài chuẩn nào đạt ngưỡng.
    scan_opt = None
    if best_fixed:
        # Đã có chiều dài MUA ĐƯỢC cắt được -> dùng luôn, KỂ CẢ khi vượt ngưỡng %.
        # Vượt ngưỡng KHÔNG phải lý do để vét cạn: vét cạn chỉ ra được chiều dài đặt
        # riêng, mà không đặt mua được thì đề xuất đó vô dụng. Cờ over_waste bên dưới
        # sẽ báo đỏ để người dùng xử lý bằng cách khác (đổi kích thước đoạn, gộp đơn...).
        chosen, source = best_fixed, "fixed"
    elif not auto_scan:
        # Không chiều dài mua được nào ĐẠT NGƯỠNG -> đây MỚI là lúc cần dò chiều dài khác.
        if timeouts:
            return {"feasible": False, "timed_out": True, "timeout_lengths": timeouts,
                    "reason": (f"Hết thời gian ở cả {len(timeouts)} chiều dài đã thử — chưa "
                               f"kết luận được. Hãy tăng thời gian chạy.")}
        return _no_solution(sizes, demands, stock_lengths, trim, kerf,
                            time_limit_sec, max_surplus, max_waste_pct)
    else:
        # Vét cạn: cũng lọc theo ĐÚNG ngưỡng người dùng -> chiều dài nào không đạt thì
        # không có nghiệm, khỏi lọt vào danh sách đề xuất.
        scan_ratio = strict_ratio
        start = max(int(min_len), int(math.ceil(max(sizes) + trim)))
        for L in range(start, int(max_len) + 1, int(step)):
            rr = optimize_material(sizes, demands, [L], trim, kerf,
                                   max_waste_ratio=scan_ratio, time_limit=time_limit_sec,
                                   max_surplus=max_surplus)
            if rr.get("feasible"):
                if scan_opt is None or (rr["waste_pct"], rr["total_bars"]) < (scan_opt["waste_pct"], scan_opt["bars"]):
                    scan_opt = {"length": L, "bars": rr["total_bars"],
                                "waste_pct": rr["waste_pct"], "result": rr}
                # Dừng sớm: đã đạt ngưỡng người dùng yêu cầu thì thôi, khỏi quét nốt dải.
                if stop_on_first and rr["waste_pct"] <= threshold + 1e-9:
                    scan_stopped_early = True
                    break
            elif rr.get("timed_out"):
                timeouts.append(L)
        if scan_opt:
            chosen, source = scan_opt, "scan"
        else:
            # (best_fixed chắc chắn None ở nhánh này — đã bị bắt ở `if best_fixed` phía trên)
            if timeouts:
                return {"feasible": False, "timed_out": True, "timeout_lengths": timeouts,
                        "reason": (f"Hết thời gian ở toàn bộ {len(timeouts)} chiều dài đã thử "
                                   f"— chưa kết luận được. Hãy tăng thời gian chạy.")}
            return _no_solution(sizes, demands, stock_lengths, trim, kerf,
                                time_limit_sec, max_surplus, max_waste_pct,
                                scanned=True)

    res = chosen["result"]
    return {
        "feasible": True,
        "cut_lengths": res["cut_lengths"], "demands": res["demands"], "produced": res["produced"],
        "best_length": chosen["length"], "source": source,
        "total_bars": res["total_bars"], "waste_pct": res["waste_pct"], "plan": res["plan"],
        "total_waste_mm": res.get("total_waste_mm", 0),          # tổng khúc thừa (phế liệu) mm
        "total_purchased_mm": res.get("total_purchased_mm", 0),
        "total_surplus_pieces": res.get("total_surplus_pieces", 0),
        "mau_nguyen_mm": res.get("mau_nguyen_mm", 0),   # khúc sắt còn nguyên -> nhập kho
        "over_waste": res["waste_pct"] > threshold + 1e-9,
        "max_waste_pct": max_waste_pct,
        # Số chiều dài bị bỏ qua vì hết giờ — nếu > 0 thì kết quả trên CHƯA chắc tối ưu.
        "timeout_count": len(timeouts),
        "timeout_lengths": timeouts[:20],
        "auto_scan": bool(auto_scan),
        # True = dừng ở chiều dài ĐẠT ngưỡng đầu tiên, chưa quét hết dải.
        "scan_stopped_early": scan_stopped_early,
        # True = chưa liệt kê hết kiểu cắt -> kết quả chưa chắc tối ưu.
        "patterns_truncated": bool(res.get("patterns_truncated")),
        # để hiển thị so sánh
        "fixed_evals": [{"length": e["length"], "bars": e["bars"], "waste_pct": e["waste_pct"]}
                        for e in fixed_evals],
        "scan_optimal": ({"length": scan_opt["length"], "bars": scan_opt["bars"],
                          "waste_pct": scan_opt["waste_pct"]} if scan_opt else None),
    }
