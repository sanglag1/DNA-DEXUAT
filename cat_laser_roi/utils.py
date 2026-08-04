def _replace_func(num, num_replace):
    if not int(num) == num: # Nếu không phải số nguyên -> return 1
        return 1
    else:
        return num_replace
    
# input: ([2360.8, 1684.8, 1289.2, 1162.2, 565, 46], 2.5)
# output: [1, 1, 1, 1, 2.5, 2.5]
def do_day_luoi_cua(list_x, num_replace):
    return [_replace_func(item, num_replace) for item in list_x]

# from optimization_logic import generate_patters, solve_patterns

# KICH_THUOC_DOAN = [2360.8, 1684.8, 1289.2, 1162.2, 565, 46]
# k_factors = [1, 1, 1, 1, 3, 3]
# LENGTH = 5850
# SL_CAT = [600, 1200, 1200, 600, 1200, 1200]
# SO_LUONG_TON_KHO = 20

# solutions = generate_patters(KICH_THUOC_DOAN, k_factors, LENGTH)
# solve_patterns(solutions, LENGTH, KICH_THUOC_DOAN, SL_CAT, SO_LUONG_TON_KHO)