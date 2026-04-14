#!/usr/bin/env python3
import os

tar_path = "/references/legacy-workflows/redis-inspection-report/redis_info.tar.gz"

print(f"检查文件: {tar_path}")
print(f"文件大小: {os.path.getsize(tar_path)} bytes")

# 读取文件头
try:
    with open(tar_path, 'rb') as f:
        # 读取前10个字节
        header = f.read(10)
        print(f"\n文件头 (十六进制): {header.hex()}")
        
        # 检查gzip魔术字节 (0x1f 0x8b)
        if header[0] == 0x1f and header[1] == 0x8b:
            print("✓ 这是一个有效的gzip文件 (魔术字节: 0x1f 0x8b)")
        else:
            print("✗ 这不是一个有效的gzip文件")
            
        # 检查压缩方法
        if len(header) > 2:
            compression_method = header[2]
            print(f"压缩方法: {compression_method} (8 = DEFLATE)")
            
except Exception as e:
    print(f"错误: {e}")