"""
Test script để chẩn đoán vấn đề với CO-2201-00249
Chạy: python test_CO2201_00249.py
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from optimization_logic import (
    get_or_calculate_patterns, 
    solve_phase2, 
    SCALING_FACTOR
)

# Data từ CO-2201-00249_ChiTiet (1).csv
DATA = [
    # (Mã mảnh, Tên đoạn, Chiều dài (mm), Số lượng)
    ("PHOI-I3.1.1", "V15 (1 tán)", 425, 100),
    ("PHOI-I3.1.2", "V15 (2 tán)", 420, 300),
    ("PHOI-I3.1.4", "V15 (1 dập)", 445, 200),
    ("PHOI-I3.1.4", "V15 (2 dập)", 400, 200),
    ("PHOI-I3.1.4", "V15 (1 dập)", 175, 200),
    ("PHOI-I3.2.1", "V15 (2 dập)", 367, 50),
    ("PHOI-I3.2.1", "V15", 367, 50),
    ("PHOI-I3.2.2", "V15", 324, 200),
    ("PHOI-I3.2.2", "V15 (4 dập)", 330, 200),
    ("PHOI-I3.2.3", "V15 (2 tán)", 367, 200),
    ("PHOI-I3.2.3", "V15", 397, 200),
    ("PHOI-I5.1.1", "V15", 850, 100),
    ("PHOI-I5.1.2", "V15", 420, 600),
    ("PHOI-I5.1.4", "V15", 870, 200),
    ("PHOI-I5.1.4", "V15", 400, 700),
    ("PHOI-I5.1.4", "V15", 175, 600),
    ("PHOI-I5.2.1", "V15", 425, 200),
    ("PHOI-I5.2.4", "V15", 445, 400),
    ("PHOI-I5.3.1", "V15", 365, 200),
    ("PHOI-I5.3.1", "V15", 405, 100),
    ("PHOI-I5.3.1", "V15", 375, 100),
    ("PHOI-I5.3.2", "V15", 665, 200),
    ("PHOI-I5.3.2", "V15", 145, 400),
]

# Gộp theo chiều dài (vì thuật toán chỉ quan tâm chiều dài)
MERGED_DATA_BY_LENGTH = {}
for ma, ten, length, qty in DATA:
    if length not in MERGED_DATA_BY_LENGTH:
        MERGED_DATA_BY_LENGTH[length] = {
            'names': [],
            'qty': 0
        }
    MERGED_DATA_BY_LENGTH[length]['names'].append(f"{ma}-{ten}")
    MERGED_DATA_BY_LENGTH[length]['qty'] += qty

# Chuyển thành các list riêng
piece_lengths = list(MERGED_DATA_BY_LENGTH.keys())
demands_list = [v['qty'] for v in MERGED_DATA_BY_LENGTH.values()]
piece_names = [f"{k}mm" for k in piece_lengths]
priorities_list = [1] * len(piece_lengths)
is_doan_cuoi = [False] * len(piece_lengths)

print("=" * 60)
print("PHÂN TÍCH DỮ LIỆU CO-2201-00249")
print("=" * 60)
print(f"Số loại đoạn (sau gộp): {len(piece_lengths)}")
print(f"Tổng số lượng cần: {sum(demands_list):,}")
print(f"Đoạn nhỏ nhất: {min(piece_lengths)}mm")
print(f"Đoạn lớn nhất: {max(piece_lengths)}mm")
print()

for i, (length, data) in enumerate(MERGED_DATA_BY_LENGTH.items()):
    print(f"  {i+1}. {length}mm × {data['qty']} = {length * data['qty']:,}mm tổng")

print()
print("=" * 60)
print("TEST 1: Chạy với stock_length = 9000mm")
print("=" * 60)

stock_length = 9000
kerf_width = 1
max_waste_percentage = 0.05  # 5%
trim_start = 10
doan_thua_cat_tay = 0
pattern_limit = 200000

# Phase 1: Tìm patterns
patterns = get_or_calculate_patterns(
    stock_length=stock_length,
    piece_lengths=piece_lengths,
    kerf_width=kerf_width,
    max_waste_percentage=max_waste_percentage,
    trim_start=trim_start,
    doan_thua_cat_tay=doan_thua_cat_tay,
    pattern_limit=pattern_limit
)

if patterns is not None:
    print(f"\n✅ Phase 1 OK: Tìm được {len(patterns):,} patterns")
    print(f"   Hao hụt min: {patterns['Hao hụt (mm)'].min() / SCALING_FACTOR:.1f}mm")
    print(f"   Hao hụt max: {patterns['Hao hụt (mm)'].max() / SCALING_FACTOR:.1f}mm")
    
    # Kiểm tra xem từng loại đoạn có xuất hiện trong patterns không
    print("\n📊 Kiểm tra từng loại đoạn trong patterns:")
    for i, length in enumerate(piece_lengths):
        col = f'segment_{i}'
        max_count = patterns[col].max()
        has_any = (patterns[col] > 0).sum()
        print(f"   {length}mm: max {max_count} đoạn/pattern, có trong {has_any:,} patterns")
    
    # Phase 2: Test với nhiều max_surplus khác nhau
    for max_surplus in [150, 300, 500, 1000]:
        print(f"\n{'='*60}")
        print(f"TEST Phase 2 với max_surplus = {max_surplus}")
        print(f"{'='*60}")
        
        result = solve_phase2(
            raw_stock_length=stock_length,
            patterns_df=patterns.copy(),
            piece_names=piece_names,
            piece_lengths=piece_lengths,
            demands_list=demands_list,
            priorities_list=priorities_list,
            max_surplus=max_surplus,
            use_priority_constraint=False,
            is_doan_cuoi=is_doan_cuoi,
            time_limit_seconds=120,
            optimal_stock_info=None
        )
        
        if result:
            print(f"\n✅ THÀNH CÔNG!")
            print(f"   Số cây sắt: {result['total_bars']}")
            print(f"   Hao hụt: {result['waste_percentage']:.2f}%")
            print(f"   Tồn kho: {result['total_surplus']} đoạn")
            break
        else:
            print(f"❌ THẤT BẠI với max_surplus = {max_surplus}")
else:
    print("❌ Phase 1 thất bại!")
