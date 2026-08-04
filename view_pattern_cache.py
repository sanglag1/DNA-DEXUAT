"""
Script để xem metadata của pattern cache
"""
import os
import json
from datetime import datetime

cache_folder = "patterns_cache"

print("=== PATTERN CACHE METADATA ===\n")

if not os.path.exists(cache_folder):
    print(f"❌ Thư mục '{cache_folder}' không tồn tại")
    exit(1)

# Tìm tất cả metadata files
metadata_files = [f for f in os.listdir(cache_folder) if f.endswith('_metadata.json')]

if not metadata_files:
    print("❌ Không tìm thấy metadata file nào")
    print("\nCác file có sẵn:")
    for f in os.listdir(cache_folder):
        print(f"  - {f}")
else:
    print(f"✅ Tìm thấy {len(metadata_files)} metadata file(s):\n")
    
    # Sort by modified time (newest first)
    metadata_files.sort(key=lambda x: os.path.getmtime(os.path.join(cache_folder, x)), reverse=True)
    
    for i, meta_file in enumerate(metadata_files, 1):
        filepath = os.path.join(cache_folder, meta_file)
        
        print("=" * 80)
        print(f"📄 #{i}: {meta_file}")
        print("=" * 80)
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            
            print(f"\n📊 THÔNG TIN:")
            print(f"  Stock length: {metadata.get('stock_length', 'N/A')}mm")
            print(f"  Pattern count: {metadata.get('pattern_count', 'N/A'):,}")
            print(f"  Piece lengths: {metadata.get('piece_lengths', 'N/A')}")
            print(f"  Max waste %: {metadata.get('max_waste_percentage', 'N/A') * 100}%")
            print(f"  Kerf width: {metadata.get('kerf_width', 'N/A')}mm")
            print(f"  Trim start: {metadata.get('trim_start', 'N/A')}mm")
            
            print(f"\n⚙️ CẤU HÌNH:")
            print(f"  Quick mode: {metadata.get('quick_mode', 'N/A')}")
            print(f"  Limit used: {metadata.get('limit_used', 'N/A'):,}")
            print(f"  Input hash: {metadata.get('input_hash', 'N/A')}")
            
            print(f"\n📅 THỜI GIAN:")
            created_at = metadata.get('created_at', 'N/A')
            if created_at != 'N/A':
                try:
                    dt = datetime.fromisoformat(created_at)
                    print(f"  Created at: {dt.strftime('%Y-%m-%d %H:%M:%S')}")
                except:
                    print(f"  Created at: {created_at}")
            else:
                print(f"  Created at: N/A")
            
            # File size
            pkl_file = filepath.replace('_metadata.json', '.pkl')
            if os.path.exists(pkl_file):
                size_mb = os.path.getsize(pkl_file) / (1024 * 1024)
                print(f"\n💾 FILE SIZE:")
                print(f"  Pickle file: {size_mb:.2f} MB")
            
            print()
            
        except Exception as e:
            print(f"❌ Lỗi đọc file: {str(e)}\n")

print("=" * 80)
print("\n💡 TIP: Xóa cache cũ để tiết kiệm dung lượng:")
print("   del patterns_cache\\*.pkl")
print("   del patterns_cache\\*_metadata.json")
