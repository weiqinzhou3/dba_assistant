#!/usr/bin/env python3
import os
import stat
import time
import sys

def get_file_info(filepath):
    """获取文件的详细信息"""
    try:
        stat_info = os.stat(filepath)
        
        # 文件大小
        size = stat_info.st_size
        
        # 权限信息
        mode = stat_info.st_mode
        permissions = stat.filemode(mode)
        
        # 所有者信息
        uid = stat_info.st_uid
        gid = stat_info.st_gid
        
        # 时间信息
        atime = time.ctime(stat_info.st_atime)  # 访问时间
        mtime = time.ctime(stat_info.st_mtime)  # 修改时间
        ctime = time.ctime(stat_info.st_ctime)  # 创建时间
        
        # 文件类型
        if stat.S_ISDIR(mode):
            file_type = "目录"
        elif stat.S_ISREG(mode):
            file_type = "普通文件"
        elif stat.S_ISLNK(mode):
            file_type = "符号链接"
        else:
            file_type = "其他类型"
        
        return {
            "文件路径": filepath,
            "文件类型": file_type,
            "文件大小": f"{size} 字节 ({size/1024:.2f} KB, {size/(1024*1024):.2f} MB)",
            "权限": permissions,
            "用户ID": uid,
            "组ID": gid,
            "最后访问时间": atime,
            "最后修改时间": mtime,
            "创建时间": ctime,
            "inode编号": stat_info.st_ino,
            "硬链接数": stat_info.st_nlink
        }
        
    except Exception as e:
        return {"错误": str(e)}

if __name__ == "__main__":
    if len(sys.argv) > 1:
        filepath = sys.argv[1]
    else:
        filepath = "/references/legacy-workflows/redis-inspection-report/redis_info.tar.gz"
    
    info = get_file_info(filepath)
    
    print("=" * 60)
    print("文件详细信息")
    print("=" * 60)
    
    for key, value in info.items():
        print(f"{key:15}: {value}")
    
    print("=" * 60)