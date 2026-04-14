#!/usr/bin/env python3
import os
import subprocess

tar_path = "/references/legacy-workflows/redis-inspection-report/redis_info.tar.gz"

print(f"检查文件: {tar_path}")
print(f"文件存在: {os.path.exists(tar_path)}")

if os.path.exists(tar_path):
    # 使用file命令检查文件类型
    try:
        result = subprocess.run(['file', tar_path], capture_output=True, text=True)
        print(f"\n文件类型: {result.stdout.strip()}")
    except:
        print("\n无法使用file命令")
    
    # 检查文件头
    try:
        with open(tar_path, 'rb') as f:
            header = f.read(100)
            print(f"\n文件头 (前100字节): {header.hex()}")
            print(f"ASCII表示: {header[:50]}")
    except Exception as e:
        print(f"\n读取文件头错误: {e}")