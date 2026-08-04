"""
Test script chia nhỏ CO-2201-00249 thành 2 sub-orders I3 và I5
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from optimization_logic import (
    get_or_calculate_patterns, 
    solve_phase2, 
    SCALING_FACTOR
)

# ===================================================================
# SUB-ORDER 1: I3 (11 loại -> gộp còn 10)
# ===================================================================
DATA_I3 = [
    ("PHOI-I3.1.1", "V15 (1 tán)", 425, 100),
    ("PHOI-I3.1.2", "V15 (2 tán)", 420, 300),
    ("PHOI-I3.1.4", "V15 (1 dập)", 445, 200),
    ("PHOI-I3.1.4", "V15 (2 dập)", 400, 200),
    ("PHOI-I3.1.4", "V15 (1 dập)", 175, 200),
    ("PHOI-I3.2.1", "V15 (2 dập)", 367, 50),
    ("PHOI-I3.2.1", "V15", 367, 50),  # Gộp với row trên
    ("PHOI-I3.2.2", "V15", 324, 200),
    ("PHOI-I3.2.2", "V15 (4 dập)", 330, 200),
    ("PHOI-I3.2.3", "V15 (2 tán)", 367, 200),  # Gộp với 367 ở trên
    ("PHOI-I3.2.3", "V15", 397, 200),
]

# ===================================================================
# SUB-ORDER 2: I5 (12 loại -> gộp còn 10)
# ===================================================================
DATA_I5 = [
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

def merge_by_length(data):
    """Gộp các đoạn cùng chiều dài"""
    merged = {}
    for ma, ten, length, qty in data:
        if length not in merged:
            merged[length] = {'names': [], 'qty': 0}
        merged[length]['names'].append(f"{ma}-{ten}")
        merged[length]['qty'] += qty
    
    piece_lengths = list(merged.keys())
    demands_list = [v['qty'] for v in merged.values()]
    piece_names = [f"{k}mm" for k in piece_lengths]
    return piece_lengths, demands_list, piece_names

def test_suborder(name, data, stock_length, max_surplus=100, pattern_limit=100000):
    print(f"\n{'='*60}")
    print(f"TEST SUB-ORDER: {name}")
    print(f"{'='*60}")
    
    piece_lengths, demands_list, piece_names = merge_by_length(data)
    priorities_list = [1] * len(piece_lengths)
    is_doan_cuoi = [False] * len(piece_lengths)
    
    print(f"Số loại đoạn (sau gộp): {len(piece_lengths)}")
    print(f"Tổng số lượng: {sum(demands_list):,}")
    print(f"Kích thước: {min(piece_lengths)}mm - {max(piece_lengths)}mm")
    print(f"Stock length: {stock_length}mm")
    print(f"Max surplus: {max_surplus}")
    print()
    
    for i, (length, demand) in enumerate(zip(piece_lengths, demands_list)):
        print(f"  {i+1}. {length}mm × {demand}")
    
    # Phase 1
    patterns = get_or_calculate_patterns(
        stock_length=stock_length,
        piece_lengths=piece_lengths,
        kerf_width=1,
        max_waste_percentage=0.05,
        trim_start=10,
        doan_thua_cat_tay=0,
        pattern_limit=pattern_limit
    )
    
    if patterns is None:
        print(f"❌ Phase 1 thất bại!")
        return False
    
    print(f"\n✅ Phase 1 OK: {len(patterns):,} patterns")
    
    # Phase 2
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
        print(f"\n✅ {name} THÀNH CÔNG!")
        print(f"   Số cây sắt: {result['total_bars']}")
        print(f"   Hao hụt: {result['waste_percentage']:.2f}%")
        print(f"   Tồn kho: {result['total_surplus']} đoạn")
        return True
    else:
        print(f"\n❌ {name} THẤT BẠI!")
        return False

if __name__ == "__main__":
    # Test I3 với stock_length = 6000mm (max đoạn là 445mm)
    result_i3 = test_suborder(
        name="CO-2201-00249-I3",
        data=DATA_I3,
        stock_length=6000,
        max_surplus=100,
        pattern_limit=100000
    )
    
    # Test I5 với stock_length = 9000mm (có đoạn 870mm)
    result_i5 = test_suborder(
        name="CO-2201-00249-I5",
        data=DATA_I5,
        stock_length=9000,
        max_surplus=100,
        pattern_limit=100000
    )
    
    print("\n" + "="*60)
    print("TỔNG KẾT")
    print("="*60)
    print(f"I3: {'✅ OK' if result_i3 else '❌ FAIL'}")
    print(f"I5: {'✅ OK' if result_i5 else '❌ FAIL'}")
