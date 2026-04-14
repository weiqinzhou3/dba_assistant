#!/usr/bin/env python3
import os
import stat

# 文件路径
file_path = "/references/legacy-workflows/redis-inspection-report/redis_info.tar.gz"

print("=" * 60)
print("文件属性检查")
print("=" * 60)

try:
    # 检查文件是否存在
    if os.path.exists(file_path):
        print(f"✓ 文件存在: {file_path}")
        
        # 获取文件状态
        stat_info = os.stat(file_path)
        
        # 文件大小
        size = stat_info.st_size
        print(f"文件大小: {size} 字节")
        print(f"        : {size/1024:.2f} KB")
        print(f"        : {size/(1024*1024):.2f} MB")
        
        # 权限
        mode = stat_info.st_mode
        print(f"权限模式: {oct(mode)}")
        
        # 人类可读的权限
        permissions = ''
        permissions += 'd' if stat.S_ISDIR(mode) else '-'
        permissions += 'r' if mode & stat.S_IRUSR else '-'
        permissions += 'w' if mode & stat.S_IWUSR else '-'
        permissions += 'x' if mode & stat.S_IXUSR else '-'
        permissions += 'r' if mode & stat.S_IRGRP else '-'
        permissions += 'w' if mode & stat.S_IWGRP else '-'
        permissions += 'x' if mode & stat.S_IXGRP else '-'
        permissions += 'r' if mode & stat.S_IROTH else '-'
        permissions += 'w' if mode & stat.S_IWOTH else '-'
        permissions += 'x' if mode & stat.S_IXOTH else '-'
        print(f"权限   : {permissions}")
        
        # 所有者和组
        print(f"用户ID : {stat_info.st_uid}")
        print(f"组ID   : {stat_info.st_gid}")
        
        # 时间信息
        import time
        print(f"最后访问: {time.ctime(stat_info.st_atime)}")
        print(f"最后修改: {time.ctime(stat_info.st_mtime)}")
        print(f"创建时间: {time.ctime(stat_info.st_ctime)}")
        
        # 检查文件类型
        print(f"文件类型: ", end="")
        if stat.S_ISREG(mode):
            print("普通文件")
        elif stat.S_ISDIR(mode):
            print("目录")
        elif stat.S_ISLNK(mode):
            print("符号链接")
        else:
            print("其他")
            
        # 检查是否是有效的gzip文件
        print("\n检查文件头...")
        with open(file_path, 'rb') as f:
            header = f.read(2)
            if header == b'\x1f\x8b':
                print("✓ 有效的gzip文件头 (0x1f 0x8b)")
            else:
                print(f"⚠ 非标准gzip文件头: {header.hex()}")
                
    else:
        print(f"✗ 文件不存在: {file_path}")
        
except Exception as e:
    print(f"检查过程中发生错误: {e}")

print("=" * 60)