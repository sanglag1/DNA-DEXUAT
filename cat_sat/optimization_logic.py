import hashlib
import json
import threading
import time
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
# OR-Tools CP-SAT
from ortools.sat.python import cp_model

# Unified cache utility
from utils.cache_utils import PatternCache


# ===================================================================
# Lớp Timer (Copy từ cat_laser_roi)
# ===================================================================
class SolverTimer(threading.Thread):
    """Lớp đếm thời gian chạy cho bộ giải và gửi cập nhật ra frontend."""
    def __init__(self, total_time):
        super().__init__()
        self.total_time = total_time
        self.stop_event = threading.Event()
        self.start_time = None
        self.daemon = True

    def run(self):
        self.start_time = time.time()
        while not self.stop_event.is_set():
            elapsed = int(time.time() - self.start_time)
            if elapsed > self.total_time:
                break
            # In ra thông điệp chuẩn để frontend bắt
            print(f"TIMER_UPDATE::{elapsed}::{int(self.total_time)}")
            time.sleep(1)

    def stop(self):
        self.stop_event.set()


# ===================================================================
# Lớp Tối Ưu Hóa (Phần 1: cache + tìm pattern)
# ===================================================================
class SteelCuttingOptimizer:
    # __init__ vẫn nhận time_limit_seconds
    def __init__(
        self,
        length,
        te_dau_sat,
        piece_names,         # <-- THÊM
        segment_sizes,
        demands,
        blade_width,
        factors,
        max_manual_cuts,
        max_stock_over,
        hao_hut_percent=1.0,
        time_limit_seconds=30.0,
        no_bundle_constraint=False,
    ):
        self.length = length
        self.te_dau_sat = te_dau_sat
        self.piece_names = piece_names  # <-- THÊM
        self.segment_sizes = np.array(segment_sizes)
        self.demands = np.array(demands)
        self.blade_width = blade_width
        # đảm bảo factors có [1, 0] để khống chế cắt tay và “không chọn”
        # (GĐ2 sẽ tự lọc factor==0 để tránh biến vô nghĩa)
        self.factors = sorted(list(set(factors)), reverse=True) + [1, 0] # Dùng set để loại trùng
        self.max_manual_cuts = max_manual_cuts
        self.max_stock_over = max_stock_over
        self.hao_hut_percent = hao_hut_percent
        self.time_limit_seconds = time_limit_seconds
        self.no_bundle_constraint = no_bundle_constraint

        self.solutions = []
        self.solution_matrix = None

        # ---- Cache setup using unified PatternCache ----
        self._cache = PatternCache()

    # -------------- Cache helpers --------------
    def _cache_key(self):
        payload = {
            "length": int(self.length),
            "segment_sizes": list(map(float, self.segment_sizes.tolist())),
            "blade_width": float(self.blade_width),
            "te_dau_sat": float(self.te_dau_sat),  # Thêm tề đầu sắt vào cache key
            "hao_hut_percent": float(self.hao_hut_percent),  # Thêm hao hụt % vào cache key
        }
        return PatternCache.generate_cache_key(payload, use_md5=True)

    def save_solution_to_pickle(self):
        """Lưu list[(obj_value, solution)] vào file pickle."""
        key = self._cache_key()
        metadata = {
            "module": "cat_sat",
            "length": self.length,
            "segment_sizes": list(map(float, self.segment_sizes.tolist())),
            "blade_width": self.blade_width,
            "te_dau_sat": self.te_dau_sat,  # Thêm tề đầu sắt vào metadata
        }
        self._cache.save(key, self.solutions, metadata)

    def cut_list(self, lst, x, length):
        """Áp tề đầu: bỏ các pattern có obj_value + te_dau > length."""
        for i, (obj_value, solution) in enumerate(lst):
            if obj_value + x <= length:
                return lst[i:]
        return []

    def load_solution_from_pickle(self):
        key = self._cache_key()
        list_solutions = self._cache.load(key)
        
        if list_solutions is None:
            return []

        print("------------------------------------------------<br>")
        print(f"ĐÃ CÓ {len(list_solutions)} NGHIỆM TRONG CACHE<br>")
        print("------------------------------------------------<br>")

        # Áp tề đầu
        list_solutions = self.cut_list(list_solutions, self.te_dau_sat, self.length)

        # VÌ MCTD CHỈ NHẬP TỐI ĐA 5 INPUT
        # Lọc theo tiêu chí <=5 loại đoạn khác 0 khi có >5 size
        if len(self.segment_sizes) > 5:
            filtered = [
                (obj_value, solution)
                for obj_value, solution in list_solutions
                if sum(1 for x in solution if x != 0) <= 5
            ]
            return filtered
        else:
            return list_solutions


# =========================================================
# GIAI ĐOẠN 1: Thu thập nghiệm bằng SolutionCallback
# =========================================================
class SolutionAndLogCollector(cp_model.CpSolverSolutionCallback):
    def __init__(
        self,
        vars_x,
        seg_scaled,
        blade_scaled,
        scale,
        length,
        te_dau_sat,
        exclude_set,
        accept_at_most=1000,
        print_every=100,
    ):
        super().__init__()
        self._vars_x = vars_x
        self._seg_scaled = seg_scaled
        self._blade_scaled = blade_scaled
        self._scale = scale
        self._length = length
        self._te = te_dau_sat
        self._exclude = exclude_set  # set(tuple(x))
        self._seen = set()
        self._solutions = []  # list[(obj_value, [x_i,...])]
        self._accept_at_most = accept_at_most
        self._print_every = max(1, print_every)
        self._cnt = 0
        self._start = time.time()

    def on_solution_callback(self):
        # đọc nghiệm
        x = [int(self.Value(v)) for v in self._vars_x]
        key = tuple(x)

        # bỏ nghiệm trùng hoặc đã có trong cache
        if key in self._seen or key in self._exclude:
            return

        # tính objective ở thang float
        sum_x = sum(x)
        obj_scaled = sum(self._seg_scaled[i] * x[i] for i in range(len(x))) + self._blade_scaled * sum_x
        obj_value = obj_scaled / self._scale  # mm

        self._solutions.append((obj_value, x))
        self._seen.add(key)

        self._cnt += 1
        if self._cnt % self._print_every == 0:
            hao_hut = self._length - obj_value
            print(f"{x}, HH {hao_hut}/cây<br>")

        # dừng sớm khi đủ số nghiệm mong muốn
        if len(self._solutions) >= self._accept_at_most:
            self.StopSearch()

    @property
    def solutions(self):
        # sắp xếp theo obj_value giảm dần để ưu tiên phương án hao hụt nhỏ
        return sorted(self._solutions, key=lambda t: t[0], reverse=True)


class SteelCuttingOptimizer(SteelCuttingOptimizer):  # extend class ở trên để gom file một chỗ
    # -----------------------------
    # Batch tìm nghiệm dùng callback
    # -----------------------------
    def _solve_single_bar_batch(self, max_solutions=1000, time_limit_sec=None):
        """
        Tạo mô hình thỏa mãn với ràng buộc:
          - Cận trên = length - te_dau_sat
          - Tổng sắt dùng = các đoạn + hao hụt lưỡi
          - Hao hụt = length - tổng sắt dùng
        """
        print(f"Bắt đầu GĐ 1: Tìm các pattern (tối đa {max_solutions:,} phương án). Vui lòng chờ...<br>")
        model = cp_model.CpModel()

        n = len(self.segment_sizes)
        vars_x = [model.NewIntVar(0, 30, f"x_{i}") for i in range(n)]
        sum_x = cp_model.LinearExpr.Sum(vars_x)

        # scale integer hóa
        scale = 10
        seg_scaled = [int(round(s * scale)) for s in self.segment_sizes.tolist()]
        blade_scaled = int(round(self.blade_width * scale))
        length_scaled = int(round(self.length * scale))
        te_scaled = int(round(self.te_dau_sat * scale))

        # Tổng sắt dùng = các đoạn + hao hụt lưỡi (KHÔNG tính te_dau_sat)
        total_material_scaled = cp_model.LinearExpr.Sum(
            [seg_scaled[i] * vars_x[i] for i in range(n)]
        ) + blade_scaled * sum_x

        # Cận trên: tổng sắt dùng <= length - te_dau_sat
        usable_length = length_scaled - te_scaled
        model.Add(total_material_scaled <= usable_length)
        
        min_material = int(round(length_scaled * (1 - self.hao_hut_percent / 100))) # Hao hụt theo % người dùng nhập
        model.Add(total_material_scaled >= min_material)

        # Bật enumerate all solutions (bài toán thỏa mãn)
        solver = cp_model.CpSolver()
        solver.parameters.enumerate_all_solutions = True
        solver.parameters.log_search_progress = True

        # KHÔNG dùng time limit cho GĐ1 (đã bỏ)
        # solver.parameters.num_search_workers = 8 # Enumerating all solutions does not work in parallel

        # chuẩn bị exclude từ cache hiện có (nếu có)
        exclude_set = set()
        for _, sol in self.solutions:
            exclude_set.add(tuple(int(v) for v in sol))

        collector = SolutionAndLogCollector(
            vars_x=vars_x,
            seg_scaled=seg_scaled,
            blade_scaled=blade_scaled,
            scale=scale,
            length=self.length,
            te_dau_sat=self.te_dau_sat,
            exclude_set=exclude_set,
            accept_at_most=max_solutions,
            print_every=100,
        )

        # chạy tìm tất cả nghiệm (giới hạn bởi solution_limit)
        solver.SearchForAllSolutions(model, collector)

        print(f"GĐ 1: Tìm thấy {len(collector.solutions)} patterns.<br>")
        return collector.solutions

    # load nghiệm từ pickle và lọc lại theo điều kiện
    def optimize_cutting(self):
        # Ưu tiên dùng nghiệm cache (sau khi lọc theo tề đầu)
        self.solutions = self.load_solution_from_pickle()

        if not self.solutions:
            print("Chưa có nghiệm trong CACHE, đang tìm nghiệm<br>")
        elif 0 < len(self.solutions) < 10:
            print("DANH SÁCH NGHIỆM QUÁ NHỎ, ĐANG GIẢI LẠI!!!!<br>")
            self.solutions = []

        # Nếu cache chưa đủ, dùng batch callback để lấy nhanh nghiệm mới
        if not self.solutions:
            MAX_SOLUTIONS = 300000
            batch = self._solve_single_bar_batch(
                max_solutions=MAX_SOLUTIONS,
                time_limit_sec=None
            )
            if not batch:
                raise ValueError("Không tìm được nghiệm phù hợp cho 1 cây sắt (GĐ 1).")


            # === LỌC NGHIỆM THEO TỀ ĐẦU SẮT (Hao hụt >= Tề đầu) ===
            # Pattern hợp lệ phải có phần dư đủ để cắt tề đầu
            before_te = len(batch)
            batch = [
                (obj, sol) for obj, sol in batch
                if obj + self.te_dau_sat <= self.length + 1e-5
            ]
            if len(batch) < before_te:
                print(f"GĐ 1: Đã lọc {before_te - len(batch)} patterns có hao hụt < tề đầu ({self.te_dau_sat}mm).<br>")

            if not batch:
                raise ValueError(f"Không có pattern nào thỏa mãn tề đầu {self.te_dau_sat}mm.")
            

            # === LỌC NGHIỆM CHỈ GIỮ LẠI PATTERN CÓ TỐI ĐA 5 KÍCH THƯỚC ===
            if len(self.segment_sizes) > 5:
                before_count = len(batch)
                # Chỉ giữ lại các pattern mà số lượng loại đoạn cắt (x > 0) <= 5
                batch = [
                    (obj, sol) for obj, sol in batch
                    if sum(1 for x in sol if x > 0) <= 5
                ]
                print(f"GĐ 1: Đã lọc bỏ pattern quá 5 loại kích thước: {before_count} -> {len(batch)} patterns.<br>")
            # ===============================================================================

            print(f"GĐ 1: Còn lại {len(batch)} patterns sau khi lọc.<br>")
            # <<< KẾT THÚC FIX >>>


            self.solutions = batch
            # Lưu cache (đã lọc)
            self.save_solution_to_pickle()

        self.solution_matrix = np.array([sol[1] for sol in self.solutions], dtype=int)
        print("------------------------------------------------<br>")
        print(f"THỰC TẾ LOAD {len(self.solution_matrix)} NGHIỆM<br>")
        print("------------------------------------------------<br>")
        
        if len(self.solution_matrix) == 0:
             raise ValueError(f"Không tìm được pattern nào phù hợp với chiều dài {self.length}mm và tề đầu {self.te_dau_sat}mm.")
        
        return self.solutions

    # -----------------------------
    # Giai đoạn 2: Phân phối số bó (CP-SAT gọn O(n·R))
    # -----------------------------
    def optimize_distribution(self):
        # Nếu không ràng buộc bó sắt -> dùng logic đơn giản (kiểu cat_laser_roi)
        if self.no_bundle_constraint:
            return self._optimize_distribution_no_bundle()
        print("<br>Bắt đầu GĐ 2: Đang tính toán bó sắt...<br>")
        if self.solution_matrix is None:
            raise ValueError("Run optimize_cutting first to generate solution matrix.")

        # A: m x n (m = số loại đoạn, n = số pattern)
        A = self.solution_matrix.T
        L = np.array([self.length - sol[0] for sol in self.solutions], dtype=float)  # hao hụt / cây cho pattern j
        m, n = A.shape

        # Chỉ dùng các factor > 0 (0 nghĩa là không chọn)
        pos_factors = sorted([f for f in self.factors if f > 0], reverse=True)
        idx_one = None
        if 1 in pos_factors:
            idx_one = pos_factors.index(1)

        model = cp_model.CpModel()

        # Upper bound chặt cho từng (j,r) để thu gọn không gian nghiệm
        def safe_div_ceil(a, b):
            return (a + b - 1) // b

        # UB[j] = min_i ceil((demands_i + max_stock_over)/A[i,j]) với a_ij>0
        UB = []
        for j in range(n):
            caps = []
            for i in range(m):
                aij = int(A[i, j])
                if aij > 0:
                    caps.append(safe_div_ceil(int(self.demands[i]) + int(self.max_stock_over), aij))
            if caps:
                UB.append(min(caps))
            else:
                UB.append(0)  # pattern không tạo ra đoạn nào

        # Biến b[j][r] = số bó pattern j với hệ số fr (fr ∈ pos_factors)
        b = []
        for j in range(n):
            row = []
            for fr in pos_factors:
                ub = safe_div_ceil(UB[j], fr) if UB[j] > 0 else 0
                row.append(model.NewIntVar(0, max(0, ub), f"b_{j}_{fr}"))
            b.append(row)

        # Tổng số cây sắt theo pattern j: sum_r fr * b[j][r]
        def bars_of_pattern(j):
            terms = []
            for r, fr in enumerate(pos_factors):
                if fr != 0:
                    terms.append(fr * b[j][r])
            return sum(terms) if terms else 0

        # Nhu cầu từng loại đoạn (khoảng [demands, demands+max_stock_over])
        C = []
        for i in range(m):
            contrib = []
            for j in range(n):
                aij = int(A[i, j])
                if aij != 0:
                    contrib.append(aij * bars_of_pattern(j))
            Ci = model.NewIntVar(0, 10**12, f"C_{i}")
            model.Add(Ci == (sum(contrib) if contrib else 0))
            # Cho phép cả THỪA và THIỪU trong phạm vi max_stock_over
            model.Add(Ci >= max(0, int(self.demands[i]) - int(self.max_stock_over)))
            model.Add(Ci <= int(self.demands[i]) + int(self.max_stock_over))
            C.append(Ci)

        # Giới hạn số lần cắt tay (factor == 1)
        if idx_one is not None:
            manual_cuts = sum(b[j][idx_one] for j in range(n))
            model.Add(manual_cuts <= int(self.max_manual_cuts))

        # Mục tiêu: minimize hao hụt tổng + tie-break nhỏ cho số bó
        loss_terms = []
        bundle_terms = []
        for j in range(n):
            bj = bars_of_pattern(j)
            # Scale hao hụt lên 1000 để tính toán số nguyên, tránh lỗi float
            loss_terms.append(int(round(L[j] * 1000)) * bj)  
            for r in range(len(pos_factors)):
                bundle_terms.append(b[j][r])

        Loss_expr = sum(loss_terms) if loss_terms else 0
        Bundles_expr = sum(bundle_terms) if bundle_terms else 0

        # W1 lớn để ưu tiên hao hụt; W2 nhỏ để giảm số bó khi bằng điểm
        W1 = 10**6
        W2 = 1
        model.Minimize(Loss_expr * W1 + Bundles_expr * W2)

        # Giải
        solver = cp_model.CpSolver()
        solver.parameters.log_search_progress = False
        solver.parameters.max_time_in_seconds = float(self.time_limit_seconds)
        solver.parameters.num_search_workers = 8

        status = solver.Solve(model)

        print("!CLEAR!")  # Xóa log trước khi in kết quả

        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            # print("Tăng cắt tay / Tồn kho / Thời gian")
            raise ValueError("Tăng cắt tay / Tồn kho / Thời gian")

        # =================================================================
        # BẮT ĐẦU KHỐI OUTPUT MỚI (THEO PHONG CÁCH cat_laser_roi)
        # =================================================================
        
        # <-- THÊM THỜI GIAN VÀ THÔNG TIN CƠ BẢN -->
        tz_vn = timezone(timedelta(hours=7))  # Vietnam timezone UTC+7
        now = datetime.now(tz_vn)
        print(f"<b>Thời gian: {now.strftime('%d/%m/%Y %H:%M:%S')}</b><br>")
        print(f"<b>Chiều dài cây sắt:</b> {self.length}mm, <b>Tề đầu:</b> {self.te_dau_sat}mm, <b>Lưỡi cắt:</b> {self.blade_width}mm<br>")
        # <-- THÊM HỆ SỐ BÓ SẮT -->
        print(f"<b>Hệ số bó (cây/bó):</b> {', '.join(map(str, pos_factors))}<br>")

        
        # 1. Tính toán các giá trị tổng hợp
        C_vals = np.array([int(solver.Value(C[i])) for i in range(m)], dtype=int)
        b_opt = np.zeros((n, len(pos_factors)), dtype=int)
        for j in range(n):
            for r in range(len(pos_factors)):
                b_opt[j, r] = int(solver.Value(b[j][r]))
        
        tong_lan_cat = int(b_opt.sum())
        tong_cat_tay = 0
        total_bars = 0
        Loss_value = 0.0 # Hao hụt (mm)

        if idx_one is not None:
                tong_cat_tay = int(b_opt[:, idx_one].sum())

        for j in range(n):
            count_j = 0
            for r, fr in enumerate(pos_factors):
                    count_j += fr * b_opt[j, r]
            total_bars += count_j
            Loss_value += L[j] * count_j

        # 2. Tạo bảng tổng kết
        print("<h4>TỔNG KẾT CẮT TỰ ĐỘNG</h4>")
        summary = []
        for i in range(m):
            summary.append({
                "Tên sắt": self.piece_names[i],
                "Đoạn (mm)": self.segment_sizes[i],
                "SL cần (đoạn)": self.demands[i],
                "SL cắt (đoạn)": C_vals[i],
                "Tồn kho (đoạn)": C_vals[i] - self.demands[i]
            })
        
        summary_df = pd.DataFrame(summary)
        
        # Hàm highlight: đỏ nếu thiếu (âm), xanh nếu thừa (dương)
        def highlight_inventory(val):
            if isinstance(val, (int, float, np.integer)):
                if val < 0:
                    return 'color: red; font-weight: bold'
                elif val > 0:
                    return 'color: green'
            return ''
        
        summary_styler = summary_df.style.set_properties(**{'text-align': 'center'}).hide(axis="index")
        summary_styler.format({"Đoạn (mm)": lambda x: f"{x:.1f}" if x != int(x) else f"{int(x)}"})
        summary_styler.applymap(highlight_inventory, subset=['Tồn kho (đoạn)'])
        print(summary_styler.to_html(classes='table table-sm table-bordered table-striped', border=0))

        # 3. In các thông số chung
        print("<hr>")
        print(f"<b>Tổng số cây sắt cần dùng:</b> {total_bars} cây<br>")
        print(f"<b>Tổng hao hụt dài:</b> {Loss_value / 1000:,.2f}m<br>")
        if self.length * total_bars > 0:
            print(f"<b>Hao hụt:</b> {(Loss_value / (self.length * total_bars)) * 100:.2f}%<br>")
        
        print(f"<b>Tổng lần cắt:</b> {tong_lan_cat}<br>")
        print(f"<b>Cắt máy:</b> {total_bars - tong_cat_tay} cây, <b>Cắt tay:</b> {tong_cat_tay} cây<br>")

        # 4. Tạo bảng kế hoạch chi tiết
        plan_data = []
        for j in range(n):
            b_opt_row = b_opt[j, :]
            if b_opt_row.sum() == 0:
                continue # Bỏ qua pattern không dùng
            
            pattern_solution = self.solutions[j][1] # [x_i, ...]
            pattern_waste = L[j]
            
            # <<< FIX YÊU CẦU 2: TÍNH TỔNG SỐ CÂY SẮT CHO PATTERN NÀY >>>
            total_bars_for_pattern = 0
            for r, fr in enumerate(pos_factors):
                total_bars_for_pattern += fr * b_opt_row[r]
            
            row = {}
            row['Hao hụt<br>(mm)'] = pattern_waste
            for i in range(m):
                row[f'segment_{i}'] = pattern_solution[i]
            for r, fr in enumerate(pos_factors):
                row[f'factor_{fr}'] = b_opt_row[r]
            
            row['Tổng<br>cây'] = total_bars_for_pattern
            
            plan_data.append(row)

        if plan_data:
            plan_df = pd.DataFrame(plan_data)
            
            # Đổi tên cột
            custom_formatter_int = lambda x: f"{int(x)}" if x == int(x) else f"{x:.1f}"
            # rename_map = {f'segment_{i}': f'{self.piece_names[i]} <br>({custom_formatter_int(self.segment_sizes[i])}mm)' for i in range(m)}
            rename_map = {f'segment_{i}': f'{custom_formatter_int(self.segment_sizes[i])}' for i in range(m)}
            factor_rename_map = {f'factor_{fr}': f'<span style="white-space:nowrap">{fr}</span><br>c/b' for fr in pos_factors}
            
            plan_df.rename(columns=rename_map, inplace=True)
            plan_df.rename(columns=factor_rename_map, inplace=True)
            
            plan_df.insert(0, 'STT', np.arange(1, len(plan_df) + 1))
            
            # Sắp xếp cột
            piece_cols = list(rename_map.values())
            factor_cols = list(factor_rename_map.values())
            other_cols = ['STT', 'Hao hụt<br>(mm)']
            # <<< FIX YÊU CẦU 2: ĐỊNH NGHĨA TÊN CỘT TỔNG >>>
            total_col_name = 'Tổng<br>cây'

            # <-- LOGIC ẨN CỘT RỖNG -->
            active_factor_cols = []
            for col_name in factor_cols:
                if plan_df[col_name].sum() > 0:
                    active_factor_cols.append(col_name)
            
            # <-- SỬ DỤNG active_factor_cols THAY VÌ factor_cols -->
            # <<< FIX YÊU CẦU 2: THÊM CỘT TỔNG VÀO CUỐI >>>
            plan_df = plan_df[other_cols + piece_cols + active_factor_cols + [total_col_name]]

            # Thay thế số 0 bằng chuỗi rỗng
            # <<< FIX YÊU CẦU 2: THÊM CỘT TỔNG VÀO DANH SÁCH >>>
            for col in piece_cols + active_factor_cols + [total_col_name]: # <-- Dùng active_factor_cols
                plan_df[col] = plan_df[col].apply(lambda x: '' if x == 0 else int(x))

            print(f"<h4>KẾ HOẠCH CẮT CHI TIẾT ({len(plan_df)} loại)</h4>")
            
            plan_styler = plan_df.style.set_properties(**{'text-align': 'center', 'font-size': '1.1rem'})
            plan_styler.format({'Hao hụt<br>(mm)': "{:,.1f}"})

            plan_styler.set_properties(**{'font-weight': 'bold'}, subset=piece_cols + active_factor_cols + [total_col_name]) # <-- Dùng active_factor_cols
            plan_styler.hide(axis="index")
            
            # Thêm viền đậm (giống cat_laser_roi)
            table_styles = []
            # --- THÊM: TĂNG FONT + NOWRAP CHO TẤT CẢ Ô ---
            table_styles.append(
                {'selector': 'th, td', 'props': [('font-size', '1.1rem'), ('white-space', 'nowrap')]}
            )
            border_style = '2px solid black'
            
            if piece_cols:
                first_col_idx = plan_df.columns.get_loc(piece_cols[0])
                last_col_idx = plan_df.columns.get_loc(piece_cols[-1])
                table_styles.extend([
                    {'selector': f'th.col{first_col_idx}, td.col{first_col_idx}', 'props': [('border-left', border_style)]},
                    {'selector': f'th.col{last_col_idx}, td.col{last_col_idx}', 'props': [('border-right', border_style)]},
                    {'selector': ', '.join([f'th.col{plan_df.columns.get_loc(c)}' for c in piece_cols]), 'props': [('border-top', border_style)]},
                    {'selector': ', '.join([f'tbody tr:last-child td.col{plan_df.columns.get_loc(c)}' for c in piece_cols]), 'props': [('border-bottom', border_style)]}
                ])
            
            if active_factor_cols: # <-- Dùng active_factor_cols
                first_col_idx = plan_df.columns.get_loc(active_factor_cols[0])
                last_col_idx = plan_df.columns.get_loc(active_factor_cols[-1])
                table_styles.extend([
                    {'selector': f'th.col{first_col_idx}, td.col{first_col_idx}', 'props': [('border-left', border_style)]},
                    {'selector': f'th.col{last_col_idx}, td.col{last_col_idx}', 'props': [('border-right', border_style)]},
                    {'selector': ', '.join([f'th.col{plan_df.columns.get_loc(c)}' for c in active_factor_cols]), 'props': [('border-top', border_style)]},
                    {'selector': ', '.join([f'tbody tr:last-child td.col{plan_df.columns.get_loc(c)}' for c in active_factor_cols]), 'props': [('border-bottom', border_style)]}
                ])

            plan_styler.set_table_styles(table_styles)
            
            print(plan_styler.to_html(classes='table table-sm table-bordered table-striped', border=0))

        # =================================================================
        # KẾT THÚC KHỐI OUTPUT MỚI
        # =================================================================

        # Trả về ma trận (n x |pos_factors|) để views.py .tolist() gửi ra client
        return b_opt

    # -----------------------------
    # GĐ 2 KHÔNG RÀNG BUỘC BÓ SẮT (giống cat_laser_roi)
    # -----------------------------
    def _optimize_distribution_no_bundle(self):
        print("\n<br>Bắt đầu GĐ 2: Đang tính toán (không ràng buộc bó sắt)...<br>")
        if self.solution_matrix is None:
            raise ValueError("Run optimize_cutting first to generate solution matrix.")

        # A: m x n (m = số loại đoạn, n = số pattern)
        A = self.solution_matrix.T
        L = np.array([self.length - sol[0] for sol in self.solutions], dtype=float)  # hao hụt / cây cho pattern j
        m, n = A.shape

        model = cp_model.CpModel()

        # Biến x[j] = số cây sắt cho pattern j (không chia bó)
        x = [model.NewIntVar(0, int(sum(self.demands) * 2), f"x_{j}") for j in range(n)]

        # Ràng buộc nhu cầu: produced >= demands và <= demands + max_stock_over
        C = []
        for i in range(m):
            contrib = []
            for j in range(n):
                aij = int(A[i, j])
                if aij != 0:
                    contrib.append(aij * x[j])
            Ci = model.NewIntVar(0, 10**12, f"C_{i}")
            model.Add(Ci == (sum(contrib) if contrib else 0))
            # Cho phép cả THỪA và THIỪU trong phạm vi max_stock_over
            model.Add(Ci >= max(0, int(self.demands[i]) - int(self.max_stock_over)))
            model.Add(Ci <= int(self.demands[i]) + int(self.max_stock_over))
            C.append(Ci)

        # Mục tiêu: minimize hao hụt tổng + tie-break nhỏ cho số cây
        loss_terms = []
        for j in range(n):
            loss_terms.append(int(round(L[j] * 1000)) * x[j])

        Loss_expr = sum(loss_terms) if loss_terms else 0
        Bars_expr = sum(x)

        W1 = 10**6
        W2 = 1
        model.Minimize(Loss_expr * W1 + Bars_expr * W2)

        # Giải
        solver = cp_model.CpSolver()
        solver.parameters.log_search_progress = False
        solver.parameters.max_time_in_seconds = float(self.time_limit_seconds)
        solver.parameters.num_search_workers = 8

        status = solver.Solve(model)

        print("!CLEAR!")  # Xóa log trước khi in kết quả

        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            raise ValueError("Tăng tồn kho / Thời gian")

        # =================================================================
        # OUTPUT (KIỂU cat_laser_roi - không có cột bó sắt)
        # =================================================================

        tz_vn = timezone(timedelta(hours=7))
        now = datetime.now(tz_vn)
        print(f"<b>Thời gian: {now.strftime('%d/%m/%Y %H:%M:%S')}</b><br>")
        print(f"<b>Chiều dài cây sắt:</b> {self.length}mm, <b>Tề đầu:</b> {self.te_dau_sat}mm, <b>Lưỡi cắt:</b> {self.blade_width}mm<br>")
        print(f"<b>Chế độ:</b> Không ràng buộc bó sắt (tính theo cây)<br>")

        # Tính toán
        C_vals = np.array([int(solver.Value(C[i])) for i in range(m)], dtype=int)
        x_opt = np.array([int(solver.Value(x[j])) for j in range(n)], dtype=int)

        total_bars = int(x_opt.sum())
        Loss_value = sum(L[j] * x_opt[j] for j in range(n))

        # Bảng tổng kết
        print("<h4>TỔNG KẾT CẮT TỰ ĐỘNG</h4>")
        summary = []
        for i in range(m):
            summary.append({
                "Tên sắt": self.piece_names[i],
                "Đoạn (mm)": self.segment_sizes[i],
                "SL cần (đoạn)": self.demands[i],
                "SL cắt (đoạn)": C_vals[i],
                "Tồn kho (đoạn)": C_vals[i] - self.demands[i]
            })

        summary_df = pd.DataFrame(summary)
        
        # Hàm highlight: đỏ nếu thiếu (âm), xanh nếu thừa (dương)
        def highlight_inventory(val):
            if isinstance(val, (int, float, np.integer)):
                if val < 0:
                    return 'color: red; font-weight: bold'
                elif val > 0:
                    return 'color: green'
            return ''
        
        summary_styler = summary_df.style.set_properties(**{'text-align': 'center'}).hide(axis="index")
        summary_styler.format({"Đoạn (mm)": lambda x: f"{x:.1f}" if x != int(x) else f"{int(x)}"})
        summary_styler.applymap(highlight_inventory, subset=['Tồn kho (đoạn)'])
        print(summary_styler.to_html(classes='table table-sm table-bordered table-striped', border=0))

        # Thông số chung
        print("<hr>")
        print(f"<b>Tổng số cây sắt cần dùng:</b> {total_bars} cây<br>")
        print(f"<b>Tổng hao hụt dài:</b> {Loss_value / 1000:,.2f}m<br>")
        if self.length * total_bars > 0:
            print(f"<b>Hao hụt:</b> {(Loss_value / (self.length * total_bars)) * 100:.2f}%<br>")

        # Bảng kế hoạch chi tiết
        plan_data = []
        for j in range(n):
            if x_opt[j] == 0:
                continue

            pattern_solution = self.solutions[j][1]
            pattern_waste = L[j]

            row = {}
            row['Hao hụt<br>(mm)'] = pattern_waste
            for i in range(m):
                row[f'segment_{i}'] = pattern_solution[i]
            row['SL<br>cây sắt'] = x_opt[j]

            plan_data.append(row)

        if plan_data:
            plan_df = pd.DataFrame(plan_data)

            custom_formatter_int = lambda x: f"{int(x)}" if x == int(x) else f"{x:.1f}"
            rename_map = {f'segment_{i}': f'{custom_formatter_int(self.segment_sizes[i])}' for i in range(m)}

            plan_df.rename(columns=rename_map, inplace=True)
            plan_df.insert(0, 'STT', np.arange(1, len(plan_df) + 1))

            piece_cols = list(rename_map.values())
            other_cols = ['STT', 'Hao hụt<br>(mm)']
            sl_col = 'SL<br>cây sắt'
            plan_df = plan_df[other_cols + piece_cols + [sl_col]]

            # Thay 0 bằng rỗng
            for col in piece_cols + [sl_col]:
                plan_df[col] = plan_df[col].apply(lambda x: '' if x == 0 else int(x))

            print(f"<h4>KẾ HOẠCH CẮT CHI TIẾT ({len(plan_df)} loại)</h4>")

            plan_styler = plan_df.style.set_properties(**{'text-align': 'center', 'font-size': '1.1rem'})
            plan_styler.format({'Hao hụt<br>(mm)': "{:,.1f}"})
            plan_styler.set_properties(**{'font-weight': 'bold'}, subset=piece_cols + [sl_col])
            plan_styler.hide(axis="index")

            # Viền đậm
            table_styles = [
                {'selector': 'th, td', 'props': [('font-size', '1.1rem'), ('white-space', 'nowrap')]}
            ]
            border_style = '2px solid black'

            if piece_cols:
                first_col_idx = plan_df.columns.get_loc(piece_cols[0])
                last_col_idx = plan_df.columns.get_loc(piece_cols[-1])
                table_styles.extend([
                    {'selector': f'th.col{first_col_idx}, td.col{first_col_idx}', 'props': [('border-left', border_style)]},
                    {'selector': f'th.col{last_col_idx}, td.col{last_col_idx}', 'props': [('border-right', border_style)]},
                    {'selector': ', '.join([f'th.col{plan_df.columns.get_loc(c)}' for c in piece_cols]), 'props': [('border-top', border_style)]},
                    {'selector': ', '.join([f'tbody tr:last-child td.col{plan_df.columns.get_loc(c)}' for c in piece_cols]), 'props': [('border-bottom', border_style)]}
                ])

            plan_styler.set_table_styles(table_styles)
            print(plan_styler.to_html(classes='table table-sm table-bordered table-striped', border=0))

        # Trả về mảng 1D x_opt để views.py .tolist() gửi ra client
        return x_opt