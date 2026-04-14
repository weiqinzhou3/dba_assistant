#!/usr/bin/env python3
import tarfile
import os

tar_gz_path = "/references/legacy-workflows/redis-inspection-report/redis_info.tar.gz"

print(f"检查文件: {tar_gz_path}")

if not os.path.exists(tar_gz_path):
    print("文件不存在")
    exit(1)

try:
    with tarfile.open(tar_gz_path, "r:gz") as tar:
        print(f"\n压缩包内容 ({len(tar.getmembers())} 个项目):")
        print("-" * 60)
        
        for member in tar.getmembers():
            if member.isdir():
                print(f"[DIR]  {member.name}/")
            else:
                print(f"[FILE] {member.name} ({member.size} bytes)")
                
except Exception as e:
    print(f"错误: {e}")