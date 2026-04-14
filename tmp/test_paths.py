#!/usr/bin/env python3
import os

paths_to_test = [
    "/references/legacy-workflows/redis-inspection-report/redis_info.tar.gz",
    "/references/legacy-workflows/redis-inspection-report/redis_info.tar.gz",
    "references/legacy-workflows/redis-inspection-report/redis_info.tar.gz",
    "./references/legacy-workflows/redis-inspection-report/redis_info.tar.gz",
    "../references/legacy-workflows/redis-inspection-report/redis_info.tar.gz",
]

print("测试各种路径:")
for path in paths_to_test:
    exists = os.path.exists(path)
    print(f"  {path}: {'✓ 存在' if exists else '✗ 不存在'}")
    
# 列出目录内容
print(f"\n列出 /references/legacy-workflows/redis-inspection-report/ 目录:")
try:
    items = os.listdir("/references/legacy-workflows/redis-inspection-report/")
    for item in items:
        full_path = os.path.join("/references/legacy-workflows/redis-inspection-report/", item)
        is_file = os.path.isfile(full_path)
        size = os.path.getsize(full_path) if is_file else 0
        print(f"  {'📄' if is_file else '📁'} {item} ({size} bytes)")
except Exception as e:
    print(f"错误: {e}")