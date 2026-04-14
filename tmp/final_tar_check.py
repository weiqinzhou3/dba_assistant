#!/usr/bin/env python3
import tarfile
import os
import gzip

tar_path = "/references/legacy-workflows/redis-inspection-report/redis_info.tar.gz"

print("=" * 60)
print(f"检查文件: {tar_path}")
print("=" * 60)

if not os.path.exists(tar_path):
    print("错误: 文件不存在")
    exit(1)

file_size = os.path.getsize(tar_path)
print(f"文件大小: {file_size} 字节 ({file_size/(1024*1024):.2f} MB)")

# 方法1: 直接使用tarfile
print("\n" + "-" * 60)
print("方法1: 使用tarfile.open()")
print("-" * 60)

try:
    with tarfile.open(tar_path, "r:gz") as tar:
        members = tar.getmembers()
        print(f"找到 {len(members)} 个项目")
        
        if len(members) == 0:
            print("警告: tar文件为空")
        else:
            print("\n目录结构:")
            for member in members:
                prefix = "📁 " if member.isdir() else "📄 "
                size_info = f" ({member.size} bytes)" if not member.isdir() and member.size > 0 else ""
                print(f"  {prefix}{member.name}{size_info}")
                
except tarfile.ReadError as e:
    print(f"tarfile.ReadError: {e}")
    print("可能不是有效的tar文件")
except Exception as e:
    print(f"其他错误: {e}")

# 方法2: 先解压gzip，再读取tar
print("\n" + "-" * 60)
print("方法2: 先解压gzip")
print("-" * 60)

try:
    # 先解压到临时文件
    temp_tar = "/tmp/temp_redis.tar"
    
    with gzip.open(tar_path, 'rb') as gz_file:
        with open(temp_tar, 'wb') as tar_file:
            tar_file.write(gz_file.read())
    
    print(f"已解压到临时文件: {temp_tar}")
    print(f"临时文件大小: {os.path.getsize(temp_tar)} 字节")
    
    # 读取tar文件
    with tarfile.open(temp_tar, "r") as tar:
        members = tar.getmembers()
        print(f"找到 {len(members)} 个项目")
        
        if len(members) > 0:
            print("\n前10个项目:")
            for i, member in enumerate(members[:10], 1):
                prefix = "📁 " if member.isdir() else "📄 "
                size_info = f" ({member.size} bytes)" if not member.isdir() and member.size > 0 else ""
                print(f"  {i:2d}. {prefix}{member.name}{size_info}")
            
            if len(members) > 10:
                print(f"  ... 还有 {len(members) - 10} 个项目")
    
    # 清理临时文件
    os.remove(temp_tar)
    
except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("检查完成")
print("=" * 60)