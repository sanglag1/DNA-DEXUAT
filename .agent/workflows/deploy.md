---
description: Git push và rebuild Docker sau khi edit code
---

# Deploy Changes

Workflow tự động commit, push code lên GitHub và rebuild Docker container.

## Steps

// turbo-all

1. Stage tất cả thay đổi:
```bash
cd /home/trand/IEA/cat_sat_iea && git add -A
```

2. Commit với message tự động hoặc theo yêu cầu:
```bash
cd /home/trand/IEA/cat_sat_iea && git commit -m "Update code changes"
```

3. Push lên GitHub:
```bash
cd /home/trand/IEA/cat_sat_iea && git push origin main
```

4. Rebuild Docker:
```bash
cd /home/trand/IEA/cat_sat_iea && docker compose down && docker compose up -d --build
```

5. Xác nhận container đang chạy:
```bash
docker ps --filter name=catsat
```
