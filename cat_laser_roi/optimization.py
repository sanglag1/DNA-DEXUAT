import pandas as pd
from ortools.sat.python import cp_model

def find_efficient_cutting_patterns():
    """
    Tìm các phương án cắt có hao hụt <= 1%, đã bao gồm lưỡi cắt.
    """
    # 1. Định nghĩa dữ liệu bài toán
    stock_length = 6000
    piece_lengths = [470, 460, 445, 430, 425, 190, 25]
    kerf_width = 1
    max_waste_percentage = 0.01

    # 2. Khởi tạo mô hình
    model = cp_model.CpModel()

    # 3. Tạo biến
    num_pieces = len(piece_lengths)
    counts = [model.NewIntVar(0, 30, f'x_{i}') for i in range(num_pieces)]

    # 4. Thêm ràng buộc
    # Tính toán các giá trị tổng
    total_pieces_length = sum(counts[i] * piece_lengths[i] for i in range(num_pieces))
    total_kerf_loss = sum(counts) * kerf_width
    total_material_used = total_pieces_length + total_kerf_loss

    # Ràng buộc 1: Tổng vật liệu sử dụng không được vượt quá chiều dài cây sắt
    model.Add(total_material_used <= stock_length)

    # Ràng buộc 2: Hao hụt <= 1% (tương đương tổng sử dụng >= 99%)
    min_material_used = int(stock_length * (1 - max_waste_percentage))
    model.Add(total_material_used >= min_material_used) # <--- THÊM RÀNG BUỘC MỚI

    # 5. Khởi tạo bộ giải và callback
    solver = cp_model.CpSolver()

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

    # 6. Giải bài toán
    print(f"🚀 Bắt đầu tìm kiếm patterns (hao hụt <= {max_waste_percentage * 100}%, tối đa {stock_length * max_waste_percentage}mm)...")
    status = solver.Solve(model, solution_collector)
    print(f"Trạng thái tìm kiếm: {solver.StatusName(status)}")

    # 7. Xử lý và hiển thị kết quả
    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        print(f"✅ Tìm thấy tổng cộng {len(solution_collector.solutions)} patterns hiệu quả.")

        if not solution_collector.solutions:
            return None

        df_patterns = pd.DataFrame(solution_collector.solutions)
        column_names = {f'x_{i}': f'SL_{length}mm' for i, length in enumerate(piece_lengths)}
        df_patterns = df_patterns.rename(columns=column_names)

        # Tính toán các cột tổng hợp
        total_sl_cols = [f'SL_{length}mm' for length in piece_lengths]
        df_patterns['Tong_SL_Doan'] = df_patterns[total_sl_cols].sum(axis=1)

        df_patterns['Tong_Dai_Doan'] = 0
        for i, length in enumerate(piece_lengths):
            df_patterns['Tong_Dai_Doan'] += df_patterns[f'SL_{length}mm'] * length

        df_patterns['Tong_Cat'] = df_patterns['Tong_Dai_Doan'] + (df_patterns['Tong_SL_Doan'] * kerf_width)
        df_patterns['Con_Lai'] = stock_length - df_patterns['Tong_Cat']
        
        # Sắp xếp lại
        ordered_columns = [f'SL_{length}mm' for length in piece_lengths] + ['Tong_Cat', 'Con_Lai']
        df_patterns = df_patterns[ordered_columns].sort_values(by='Con_Lai')

        print("\nBảng tổng hợp các patterns hiệu quả nhất (hao hụt ít):")
        print(df_patterns.head())

        # Lưu kết quả
        output_file = 'efficient_cutting_patterns.pkl'
        df_patterns.to_pickle(output_file)
        print(f"\n💾 Đã lưu tất cả patterns hiệu quả vào file: '{output_file}'")
        
        return df_patterns
    else:
        print("❌ Không tìm thấy pattern nào phù hợp với các ràng buộc.")
        return None

# Chạy hàm chính
efficient_patterns = find_efficient_cutting_patterns()