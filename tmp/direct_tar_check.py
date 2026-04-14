#!/usr/bin/env python3
import tarfile
import os
import sys

# 设置文件路径
tar_path = "/references/legacy-workflows/redis-inspection-report/redis_info.tar.gz"

print(f"尝试打开文件: {tar_path}")
print(f"文件存在: {os.path.exists(tar_path)}")

if os.path.exists(tar_path):
    print(f"文件大小: {os.path.getsize(tar_path)} bytes")
    
    try:
        # 尝试打开tar.gz文件
        with tarfile.open(tar_path, "r:gz") as tar:
            print(f"\n成功打开tar.gz文件")
            print(f"文件数量: {len(tar.getmembers())}")
            
            # 列出所有文件
            print("\n文件列表:")
            for i, member in enumerate(tar.getmembers(), 1):
                if member.isdir():
                    print(f"{i:3d}. [DIR]  {member.name}/")
                else:
                    print(f"{i:3d}. [FILE] {member.name} ({member.size} bytes)")
                    
    except tarfile.ReadError as e:
        print(f"\n读取错误: {e}")
        print("可能不是有效的tar.gz文件")
    except Exception as e:
        print(f"\n其他错误: {e}")
        import traceback
        traceback.print_exc()
else:
    print("文件不存在")