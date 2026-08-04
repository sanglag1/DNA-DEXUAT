"""
Script để kiểm tra kết quả optimization trong Redis
"""
import redis
import json

# Kết nối Redis
r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

print("=== KIỂM TRA REDIS OPTIMIZATION CACHE ===\n")

# Tìm tất cả keys liên quan đến optimization
patterns = [
    "optimization:*",
    "optimal_length:*",
    "test_result:*",
    "cat_laser_roi:*"
]

all_keys = []
for pattern in patterns:
    keys = r.keys(pattern)
    all_keys.extend(keys)

if not all_keys:
    print("❌ Không tìm thấy data optimization nào trong Redis.")
    print("\nThử tìm tất cả keys:")
    all_redis_keys = r.keys("*")
    print(f"Tổng số keys trong Redis: {len(all_redis_keys)}")
    if all_redis_keys:
        print("\nMột số keys mẫu:")
        for key in all_redis_keys[:20]:
            print(f"  - {key}")
else:
    print(f"✅ Tìm thấy {len(all_keys)} keys liên quan đến optimization:\n")
    
    for key in sorted(all_keys):
        value_type = r.type(key)
        print(f"Key: {key}")
        print(f"Type: {value_type}")
        
        if value_type == 'string':
            value = r.get(key)
            try:
                # Thử parse JSON
                data = json.loads(value)
                print(f"Value (JSON): {json.dumps(data, indent=2, ensure_ascii=False)}")
            except:
                # Nếu không phải JSON, in trực tiếp
                print(f"Value: {value[:500]}")  # Giới hạn 500 ký tự
        elif value_type == 'hash':
            hash_data = r.hgetall(key)
            print(f"Hash data:")
            for field, val in hash_data.items():
                print(f"  {field}: {val}")
        elif value_type == 'list':
            list_data = r.lrange(key, 0, -1)
            print(f"List data ({len(list_data)} items):")
            for i, item in enumerate(list_data[:10]):  # Chỉ hiện 10 items đầu
                print(f"  [{i}]: {item[:200]}")
        elif value_type == 'zset':
            zset_data = r.zrange(key, 0, -1, withscores=True)
            print(f"Sorted Set data ({len(zset_data)} items):")
            for member, score in zset_data[:10]:
                print(f"  {member}: {score}")
        
        # Kiểm tra TTL
        ttl = r.ttl(key)
        if ttl > 0:
            print(f"TTL: {ttl} seconds ({ttl/3600:.1f} hours)")
        elif ttl == -1:
            print(f"TTL: No expiration")
        
        print("-" * 80)
        print()

print("\n=== TÌM KIẾM THEO HASH PATTERN ===")
# Thử tìm pattern cache
cache_keys = r.keys("patterns_*")
if cache_keys:
    print(f"Tìm thấy {len(cache_keys)} pattern cache keys (file pickle):")
    for key in cache_keys[:5]:
        print(f"  - {key}")
else:
    print("Không tìm thấy pattern cache trong Redis (chúng được lưu trong file .pkl)")

print("\n=== HOÀN TẤT ===")
