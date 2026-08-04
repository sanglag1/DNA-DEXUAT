# -*- coding: utf-8 -*-
import pandas as pd
from ortools.sat.python import cp_model
import os
import hashlib
import pickle

# ===================================================================
# GIAI ĐOẠN 1: TÌM TẤT CẢ CÁC PHƯƠNG ÁN CẮT HIỆU QUẢ
# ===================================================================
def find_efficient_cutting_patterns(stock_length, piece_lengths, kerf_width, max_waste_percentage):
	"""
	Hàm tính toán cốt lõi của Giai đoạn 1: Dùng OR-Tools để tìm patterns.
	"""
	print("\n⏳ Bắt đầu Giai đoạn 1: Tìm các phương án cắt hiệu quả...")

	model = cp_model.CpModel()
	num_pieces = len(piece_lengths)
	counts = [model.NewIntVar(0, 30, f'x_{i}') for i in range(num_pieces)]

	total_pieces_length = sum(counts[i] * length for i, length in enumerate(piece_lengths))
	total_kerf_loss = sum(counts) * kerf_width
	total_material_used = total_pieces_length + total_kerf_loss

	model.Add(total_material_used <= stock_length)
	min_material_used = int(stock_length * (1 - max_waste_percentage))
	model.Add(total_material_used >= min_material_used)
	
    #----------------------------------------------------------
	waste_var = model.NewIntVar(0, stock_length, 'waste')
	model.Add(waste_var == stock_length - total_material_used)
	# Tạo một biến boolean (chỉ có thể là True hoặc False)
	is_waste_zero = model.NewBoolVar('is_waste_zero')
    # Ràng buộc 1: NẾU is_waste_zero là True, THÌ waste_var phải bằng 0
	model.Add(waste_var == 0).OnlyEnforceIf(is_waste_zero)
    # Ràng buộc 2: NẾU is_waste_zero là False, THÌ waste_var phải >= 6
	model.Add(waste_var >= 6).OnlyEnforceIf(is_waste_zero.Not())
    #----------------------------------------------------------

	solver = cp_model.CpSolver()
	solver.log_search_progress = True
	print("\n--- LOG TỪ BỘ GIẢI (Giai đoạn 1) ---")

	class AllSolutionsCollector(cp_model.CpSolverSolutionCallback):
		def __init__(self, variables):
			cp_model.CpSolverSolutionCallback.__init__(self)
			self.__variables = variables
			self.solutions = []
		def on_solution_callback(self):
			solution = {v.Name(): self.Value(v) for v in self.__variables}
			self.solutions.append(solution)

	solution_collector = AllSolutionsCollector(counts)
	solver.parameters.enumerate_all_solutions = True
	status = solver.Solve(model, solution_collector)
	print("--- KẾT THÚC LOG ---\n")

	if status in (cp_model.OPTIMAL, cp_model.FEASIBLE) and solution_collector.solutions:
		print(f"✅ GĐ 1: Tính toán thành công, tìm thấy {len(solution_collector.solutions)} patterns hiệu quả.")
		df_patterns = pd.DataFrame(solution_collector.solutions)

		column_names = {f'x_{i}': f'{length}mm' for i, length in enumerate(piece_lengths)}
		df_patterns = df_patterns.rename(columns=column_names)

		total_sl_cols = [f'{length}mm' for length in piece_lengths]	# danh sách header
		df_patterns['Tong_SL_Doan'] = df_patterns[total_sl_cols].sum(axis=1)
		df_patterns['Tong_Dai_Doan'] = 0
		for i, length in enumerate(piece_lengths):
			df_patterns['Tong_Dai_Doan'] += df_patterns[f'{length}mm'] * length

		# Tong_Cat là tổng đã cắt được bao gồm độ dày lưỡi cưa.
		df_patterns['Tong_Cat'] = df_patterns['Tong_Dai_Doan'] + (df_patterns['Tong_SL_Doan'] * kerf_width)

		df_patterns['Hao hụt (mm)'] = stock_length - df_patterns['Tong_Cat']

		ordered_columns = [f'{length}mm' for length in piece_lengths] + ['Hao hụt (mm)']
		return df_patterns[ordered_columns].sort_values(by='Hao hụt (mm)')
	else:
		print("❌ GĐ 1: Không tìm thấy pattern nào phù hợp.")
		return None

# (Hàm get_or_calculate_patterns giữ nguyên không đổi)
def get_or_calculate_patterns(stock_length, piece_lengths, kerf_width, max_waste_percentage):
	cache_folder = "patterns_cache"
	os.makedirs(cache_folder, exist_ok=True) 
	sorted_pieces = tuple(sorted(piece_lengths))
	params_string = f"{stock_length}-{sorted_pieces}-{kerf_width}-{max_waste_percentage}"
	input_hash = hashlib.sha256(params_string.encode('utf-8')).hexdigest()[:16]
	filename = os.path.join(cache_folder, f"patterns_{input_hash}.pkl")
	if os.path.exists(filename):
		print(f"👍 GĐ 1: Đã tìm thấy file nghiệm '{filename}'. Đang tải lại...")
		with open(filename, 'rb') as f:
			patterns = pickle.load(f)
		print("✅ GĐ 1: Tải lại thành công!")
		return patterns
	else:
		patterns = find_efficient_cutting_patterns(stock_length, piece_lengths, kerf_width, max_waste_percentage)
		if patterns is not None and not patterns.empty:
			with open(filename, 'wb') as f:
				pickle.dump(patterns, f)
			print(f"\n💾 GĐ 1: Đã lưu bộ nghiệm mới vào file: '{filename}'")
		return patterns

# ===================================================================
# GIAI ĐOẠN 2: TÌM KẾ HOẠCH CẮT SẮT TỐI ƯU
# ===================================================================
def solve_phase2(STOCK_LENGTH, patterns_df, piece_lengths, demands_list, priorities_list, 
	max_surplus, use_priority_constraint=False, time_limit_seconds=120.0):
	print("\n🚀 Bắt đầu Giai đoạn 2: Tối ưu hóa kế hoạch cắt sắt...")

	if use_priority_constraint:
		print("\n--- Chế độ ưu tiên đang BẬT ---")
		long_piece_cols = [f'{length}mm' for length in piece_lengths if length >= 60]
		original_pattern_count = len(patterns_df)
		patterns_df = patterns_df[patterns_df[long_piece_cols].sum(axis=1) > 0].copy()
		print(f"Lọc pattern: Giữ lại {len(patterns_df)}/{original_pattern_count} patterns hợp lệ (có đoạn >= 60mm).")

		priority_map = dict(zip(piece_lengths, priorities_list))
		def calculate_priority_score(row):
			min_priority = float('inf')
			for length, priority in priority_map.items():
				if row[f'{length}mm'] > 0:
					if priority < min_priority:
						min_priority = priority
			return min_priority
		patterns_df['Priority_Score'] = patterns_df.apply(calculate_priority_score, axis=1)
	else:
		print("\n--- Chế độ ưu tiên đang TẮT (chỉ tối ưu hao hụt và tồn kho) ---")

	num_patterns = len(patterns_df)
	if num_patterns == 0: return

	model = cp_model.CpModel()
	max_demand_estimate = sum(demands_list) * 2
	x = [model.NewIntVar(0, max_demand_estimate, f'x_{j}') for j in range(num_patterns)]
	surplus_vars = {} 
	for i, length in enumerate(piece_lengths):
		col_name = f'{length}mm'
		# tìm số lượng cây sắt x[j] từng pattern j sao cho sumproduct là số lượng mỗi kích thước đoạn
		produced_amount = sum(x[j] * patterns_df.iloc[j][col_name] for j in range(num_patterns))
		required_amount = demands_list[i]
		model.Add(produced_amount >= required_amount)
		s = model.NewIntVar(0, max_demand_estimate, f'surplus_{length}')
		model.Add(s == produced_amount - required_amount)
		surplus_vars[length] = s
		model.Add(s <= max_surplus)

	solver = cp_model.CpSolver()
	solver.parameters.max_time_in_seconds = time_limit_seconds
	solver.parameters.log_search_progress = True

	print("\n--- ƯU TIÊN 1: Tối thiểu hóa Hao hụt ---")
	total_waste = sum(x[j] * patterns_df.iloc[j]['Hao hụt (mm)'] for j in range(num_patterns))
	model.Minimize(total_waste)
	status = solver.Solve(model)
	if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE): return
	min_waste_found = int(solver.ObjectiveValue())
	print(f"✅ Mức hao hụt tối thiểu: {min_waste_found:,.0f} mm")
	model.Add(total_waste == min_waste_found)

	print("\n--- ƯU TIÊN 2: Tối thiểu hóa Tồn kho ---")
	total_surplus = sum(surplus_vars.values())
	model.Minimize(total_surplus)
	status = solver.Solve(model)
	if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE): return
	min_surplus_found = int(solver.ObjectiveValue())
	print(f"✅ Mức tồn kho tối thiểu: {min_surplus_found:,.0f} đoạn")
	model.Add(total_surplus == min_surplus_found)

	if use_priority_constraint:
		print("\n--- ƯU TIÊN 3: Tối ưu theo Độ ưu tiên ---")
		total_priority_score = sum(x[j] * patterns_df.iloc[j]['Priority_Score'] for j in range(num_patterns))
		model.Minimize(total_priority_score)
		status = solver.Solve(model)
		if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
			print("✅ Đã tìm được lời giải tối ưu cho độ ưu tiên!")
		else:
			return

	if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
		# print("\n\n=============== KẾ HOẠCH CẮT SẮT TỐI ƯU ===============")
		plan_indices = [j for j in range(num_patterns) if solver.Value(x[j]) > 0]
		plan_counts = [solver.Value(x[j]) for j in plan_indices]

		production_plan = patterns_df.iloc[plan_indices].copy()
		production_plan['SL cây sắt'] = plan_counts

		if use_priority_constraint:
			production_plan = production_plan.sort_values(
				by=['Priority_Score', 'SL cây sắt'],
				ascending=[True, True]
			)
			print_plan = production_plan.drop(columns=['Priority_Score'])
		else:
			production_plan = production_plan.sort_values(by='SL cây sắt', ascending=True)
			print_plan = production_plan

		print(f"Chiều dài cây sắt: {STOCK_LENGTH}mm")
		print("\n KẾ HOẠCH CẮT")

		# print("📋 Các pattern được chọn và số lần thực hiện:")
		print(print_plan.to_string(index=False)) 

		print("\n\nTỔNG KẾT:")
		summary = []
		total_produced_pieces = 0
		for i, length in enumerate(piece_lengths):
			col_name = f'{length}mm'
			produced = (production_plan[col_name] * production_plan['SL cây sắt']).sum()
			required = demands_list[i]
			surplus = produced - required
			summary.append({
				"Đoạn (mm)": length,
				"SL cần (đoạn)": required,
				"SL cắt (đoạn)": produced,
				"Tồn kho (đoạn)": surplus
			})
			total_produced_pieces += produced

		summary_df = pd.DataFrame(summary)
		print(summary_df.to_string(index=False))

		total_bars_used = production_plan['SL cây sắt'].sum()
		final_waste = (production_plan['Hao hụt (mm)'] * production_plan['SL cây sắt']).sum()

		print("\n---------------------------------------------------------")
		print(f"Tổng số cây sắt cần dùng: {total_bars_used} cây")
		# print(f"Tổng số đoạn sản xuất được:      {total_produced_pieces}")
		print(f"Tổng hao hụt dài: {final_waste/1000}m")
		print(f"Hao hụt: {final_waste/(STOCK_LENGTH*total_bars_used)*100:.2f}%")
		print("=========================================================")
	else:
		print("\n❌ Rất tiếc, không thể tìm ra kế hoạch sản xuất phù hợp.")

# ===================================================================
# KHỐI LỆNH CHÍNH ĐỂ CHẠY
# ===================================================================
if __name__ == "__main__":
    # --- ĐỊNH NGHĨA CÁC THAM SỐ BÀI TOÁN TẠI ĐÂY ---
    RAW_STOCK_LENGTH = 6000 # Chiều dài cây sắt thô
    TRIM_START = 3          # Phần tề đầu bị bỏ đi
    
    STOCK_LENGTH = RAW_STOCK_LENGTH - TRIM_START

    KERF_WIDTH = 1
    MAX_WASTE_PERCENTAGE = 0.01
    USE_PRIORITY_CONSTRAINT = True
    TIME_LIMIT_SECONDS_PHASE_2 = 120

    PIECE_LENGTHS = [470, 460, 445, 430, 425, 190, 25]
    DEMANDS_LIST = [3200, 1600, 3200, 3200, 1600, 3200, 3200]
    PRIORITIES_LIST = [1, 2, 4, 2, 1, 1, 0]
    MAX_SURPLUS = 10

    print(f"--- Bắt đầu tính toán với chiều dài cây sắt hiệu dụng: {STOCK_LENGTH}mm ---")

    # --- BƯỚC 1: TÌM HOẶC TẢI LẠI CÁC PATTERNS ---
    patterns_data = get_or_calculate_patterns(
        stock_length=STOCK_LENGTH, 
        piece_lengths=PIECE_LENGTHS,
        kerf_width=KERF_WIDTH, 
        max_waste_percentage=MAX_WASTE_PERCENTAGE
    )

    # --- BƯỚC 2: NẾU CÓ PATTERNS, LẬP KẾ HOẠCH SẢN XUẤT ---
    if patterns_data is not None and not patterns_data.empty:
        solve_phase2(
            STOCK_LENGTH, # Truyền chiều dài hiệu dụng vào hàm
            patterns_data, 
            PIECE_LENGTHS, 
            DEMANDS_LIST, 
            PRIORITIES_LIST,
            MAX_SURPLUS, 
            use_priority_constraint=USE_PRIORITY_CONSTRAINT,
            time_limit_seconds=TIME_LIMIT_SECONDS_PHASE_2
        )
    else:
        print("\nKhông thể thực hiện Giai đoạn 2 vì không có dữ liệu pattern từ Giai đoạn 1.")