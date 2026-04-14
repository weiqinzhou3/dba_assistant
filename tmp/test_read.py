#!/usr/bin/env python3
import os

file_path = "/references/legacy-workflows/redis-inspection-report/redis_info.tar.gz"

print("测试文件读取...")
print(f"文件路径: {file_path}")

# 检查文件是否存在
if os.path.exists(file_path):
    print("✓ 文件存在")
    
    # 检查文件大小
    size = os.path.getsize(file_path)
    print(f"文件大小: {size} 字节")
    
    # 尝试读取前几个字节
    try:
        with open(file_path, 'rb') as f:
            first_bytes = f.read(10)
            print(f"前10字节: {first_bytes.hex()}")
            
            # 检查是否是gzip文件
            if first_bytes[:2] == b'\x1f\x8b':
                print("✓ 有效的gzip文件头")
            else:
                print("⚠ 非标准gzip文件头")
                
    except Exception as e:
        print(f"读取文件时出错: {e}")
        
else:
    print("✗ 文件不存在")