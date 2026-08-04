"""
Test với max_waste_percentage cao hơn (8-10%)
và debug xem patterns có chứa đủ các loại đoạn không
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from optimization_logic import (
    find_efficient_cutting_patterns,
    solve_phase2, 
    SCALING_FACTOR
)

# Data đơn giản hơn - chỉ 5 loại đoạn để test
DATA_SIMPLE = [
    (425, 100),
    (420, 300),
    (445, 200),
    (400, 200),
    (175, 200),
]

piece_lengths = [d[0] for d in DATA_SIMPLE]
demands_list = [d[1] for d in DATA_SIMPLE]
piece_names = [f"{l}mm" for l in piece_lengths]

print("=" * 60)
print("TEST ĐƠN GIẢN VỚI 5 LOẠI ĐOẠN")
print("=" * 60)
print(f"Đoạn: {piece_lengths}")
print(f"SL: {demands_list}")
print()

# Test với nhiều mức max_waste_percentage
for max_waste_pct in [0.05, 0.08, 0.10, 0.15]:
    print(f"\n{'='*60}")
    print(f"TEST với max_waste_percentage = {max_waste_pct*100:.0f}%")
    print(f"{'='*60}")
    
    patterns = find_efficient_cutting_patterns(
        stock_length=6000,
        piece_lengths=piece_lengths,
        kerf_width=1,
        max_waste_percentage=max_waste_pct,
        trim_start=10,
        doan_thua_cat_tay=0,
        pattern_limit=50000
    )
    
    if patterns is None or patterns.empty:
        print("❌ Không tìm thấy pattern nào!")
        continue
    
    print(f"✅ Tìm được {len(patterns):,} patterns")
    
    # Kiểm tra từng loại đoạn có xuất hiện trong patterns không
    print("\n📊 Kiểm tra coverage:")
    all_covered = True
    for i, length in enumerate(piece_lengths):
        col = f'segment_{i}'
        has_any = (patterns[col] > 0).sum()
        max_count = patterns[col].max()
        if has_any == 0:
            all_covered = False
            print(f"   ❌ {length}mm: KHÔNG CÓ trong bất kỳ pattern nào!")
        else:
            print(f"   ✅ {length}mm: có trong {has_any:,} patterns (max {max_count} đoạn/pattern)")
    
    if not all_covered:
        print("\n⚠️ Một số đoạn không có trong patterns - không thể tối ưu!")
        continue
    
    # Test Phase 2
    print("\n🚀 Chạy Phase 2...")
    result = solve_phase2(
        raw_stock_length=6000,
        patterns_df=patterns.copy(),
        piece_names=piece_names,
        piece_lengths=piece_lengths,
        demands_list=demands_list,
        priorities_list=[1] * len(piece_lengths),
        max_surplus=200,
        use_priority_constraint=False,
        is_doan_cuoi=[False] * len(piece_lengths),
        time_limit_seconds=60,
        optimal_stock_info=None
    )
    
    if result:
        print(f"\n✅ THÀNH CÔNG!")
        print(f"   Số cây: {result['total_bars']}")
        print(f"   Hao hụt: {result['waste_percentage']:.2f}%")
        break
    else:
        print("❌ Phase 2 thất bại!")
