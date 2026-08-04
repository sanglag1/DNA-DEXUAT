from ortools.linear_solver import pywraplp # type: ignore

# Định nghĩa các thông số
stock_length = 100  # Chiều dài thanh gỗ
lengths = [20, 30, 40]  # Chiều dài các loại thanh cần cắt
demands = [14, 10, 8]  # Nhu cầu cho từng loại thanh

# Khởi tạo solver cho lập trình tuyến tính (LP)
solver = pywraplp.Solver.CreateSolver('GLOP')

# Khởi tạo các mẫu cắt ban đầu
patterns = [
    [5, 0, 0],  # 5 thanh 20cm
    [0, 3, 0],  # 3 thanh 30cm
    [0, 0, 2]  # 2 thanh 40cm
]

# Thiết lập biến cho các mẫu cắt
x = [solver.NumVar(0, solver.infinity(), f'x{i}') for i in range(len(patterns))]

# Ràng buộc: Đáp ứng nhu cầu
for i in range(len(demands)):
    solver.Add(sum(patterns[j][i] * x[j] for j in range(len(patterns))) >= demands[i])

# Hàm mục tiêu: Tối thiểu hóa số thanh gỗ
objective = solver.Objective()
for var in x:
    objective.SetCoefficient(var, 1)
objective.SetMinimization()

# Giải LP thư giãn và lặp để tạo cột mới
status = solver.Solve()
while status == solver.OPTIMAL:
    # Lấy giá trị kép (dual values)
    duals = [solver.constraints()[i].DualValue() for i in range(len(demands))]

    # Giải bài toán con (knapsack) để tìm mẫu cắt mới
    knapsack_solver = pywraplp.Solver.CreateSolver('SCIP')
    y = [knapsack_solver.IntVar(0, stock_length // lengths[i], f'y{i}') for i in range(len(lengths))]
    knapsack_solver.Add(sum(lengths[i] * y[i] for i in range(len(lengths))) <= stock_length)
    knapsack_objective = knapsack_solver.Objective()
    for i in range(len(lengths)):
        knapsack_objective.SetCoefficient(y[i], duals[i])
    knapsack_objective.SetMaximization()
    knapsack_status = knapsack_solver.Solve()

    # Nếu tìm được mẫu cắt mới cải thiện giải pháp
    if knapsack_status == knapsack_solver.OPTIMAL and knapsack_objective.Value() > 1:
        new_pattern = [int(y[i].solution_value()) for i in range(len(lengths))]
        patterns.append(new_pattern)
        # Thêm biến mới
        new_x = solver.NumVar(0, solver.infinity(), f'x{len(patterns) - 1}')
        x.append(new_x)
        # Cập nhật ràng buộc và hàm mục tiêu
        for i in range(len(demands)):
            solver.constraints()[i].SetCoefficient(new_x, new_pattern[i])
        objective.SetCoefficient(new_x, 1)
        status = solver.Solve()
    else:
        break

# In kết quả
print("Giải pháp tối ưu:")
for i, var in enumerate(x):
    print(f"Mẫu {i}: {var.solution_value()}")
print(f"Tổng số thanh gỗ: {sum(var.solution_value() for var in x)}")