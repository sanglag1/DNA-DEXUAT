"""
Script để xem kết quả optimization từ Redis
"""
import redis
import json
from datetime import datetime

# Kết nối Redis
r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

print("=== XEM KẾT QUẢ OPTIMIZATION TỪ REDIS ===\n")

# Tìm tất cả session keys
session_keys = r.keys("optimization:*:meta")

if not session_keys:
    print("❌ Không tìm thấy session optimization nào trong Redis.")
    print("Hãy chạy optimization với tính năng lưu Redis được bật.\n")
else:
    print(f"✅ Tìm thấy {len(session_keys)} session(s):\n")
    
    for meta_key in sorted(session_keys, reverse=True):  # Mới nhất lên đầu
        session_key = meta_key.replace(':meta', '')
        
        print("=" * 80)
        print(f"📊 SESSION: {session_key}")
        print("=" * 80)
        
        # Lấy metadata
        meta = r.hgetall(meta_key)
        if meta:
            print("\n📋 METADATA:")
            print(f"  Last test: {meta.get('last_test', 'N/A')}mm")
            print(f"  Total tests: {meta.get('total_tests', 'N/A')}")
            print(f"  Completed tests: {meta.get('completed_tests', 'N/A')}")
            print(f"  Last update: {meta.get('last_update', 'N/A')}")
        
        # Lấy kết quả cuối cùng
        final_key = f"{session_key}:final"
        final_result = r.hgetall(final_key)
        if final_result:
            print("\n🎯 KẾT QUẢ CUỐI CÙNG:")
            print(f"  ✅ Chiều dài tối ưu: {final_result.get('optimal_length', 'N/A')}mm")
            print(f"  📊 Hao hụt: {final_result.get('waste_percentage', 'N/A')}%")
            print(f"  📦 Số cây sắt: {final_result.get('total_bars', 'N/A')} cây")
            print(f"  📈 Tồn kho: {final_result.get('total_surplus', 'N/A')} đoạn")
            print(f"  ⏱️ Hoàn thành: {final_result.get('completed_at', 'N/A')}")
            print(f"  🔍 Tests completed: {final_result.get('valid_results', 'N/A')}/{final_result.get('total_tests', 'N/A')}")
        else:
            print("\n⚠️ Chưa có kết quả cuối cùng (có thể đang chạy hoặc bị gián đoạn)")
        
        # Lấy tất cả kết quả tests
        results_key = f"{session_key}:results"
        all_results = r.hgetall(results_key)
        
        if all_results:
            print(f"\n📈 CHI TIẾT CÁC TESTS ({len(all_results)} kết quả):")
            
            # Parse và sắp xếp theo hao hụt
            parsed_results = []
            for length, result_json in all_results.items():
                try:
                    result = json.loads(result_json)
                    parsed_results.append(result)
                except:
                    pass
            
            # Sắp xếp theo waste_pct tăng dần
            parsed_results.sort(key=lambda x: x.get('waste_pct', 999))
            
            # Hiển thị top 10 tốt nhất
            print("\n  🏆 TOP 10 KẾT QUẢ TỐT NHẤT:")
            print(f"  {'Chiều dài':>12} | {'Hao hụt':>10} | {'Số cây':>8} | {'Tồn kho':>10}")
            print(f"  {'-'*12}-+-{'-'*10}-+-{'-'*8}-+-{'-'*10}")
            
            for i, res in enumerate(parsed_results[:10], 1):
                length = res.get('length', 0)
                waste = res.get('waste_pct', 0)
                bars = res.get('bars', 0)
                surplus = res.get('total_surplus', 0)
                marker = " ⭐" if i == 1 else ""
                print(f"  {length:>12}mm | {waste:>9.2f}% | {bars:>8} | {surplus:>10}{marker}")
            
            if len(parsed_results) > 10:
                print(f"\n  ... và {len(parsed_results) - 10} kết quả khác")
        
        print("\n")

print("=" * 80)
print("💡 TIP: Để xóa session cũ: redis-cli DEL 'optimization:YYYYMMDD_HHMMSS:*'")
print("=" * 80)
