#!/usr/bin/env python3
import tarfile
import os
import json

# 源文件路径
tar_gz_path = "/references/legacy-workflows/redis-inspection-report/redis_info.tar.gz"
extract_to = "/tmp/redis_inspection_extract"

print(f"正在检查文件: {tar_gz_path}")

# 检查文件是否存在
if not os.path.exists(tar_gz_path):
    print(f"错误: 文件不存在")
    exit(1)

# 获取文件大小
file_size = os.path.getsize(tar_gz_path)
print(f"文件大小: {file_size} 字节 ({file_size/(1024*1024):.2f} MB)")

# 创建提取目录
os.makedirs(extract_to, exist_ok=True)
print(f"创建提取目录: {extract_to}")

# 打开tar.gz文件并列出内容
try:
    print("\n正在读取压缩包内容...")
    with tarfile.open(tar_gz_path, "r:gz") as tar:
        # 获取所有成员
        members = tar.getmembers()
        print(f"压缩包中包含 {len(members)} 个文件/目录")
        
        print("\n文件列表:")
        print("-" * 80)
        
        file_list = []
        dir_list = []
        
        for i, member in enumerate(members, 1):
            if member.isdir():
                dir_list.append(member.name)
                print(f"{i:3d}. [目录] {member.name}/")
            else:
                file_list.append({
                    "name": member.name,
                    "size": member.size,
                    "size_mb": member.size/(1024*1024)
                })
                size_info = f" ({member.size/(1024*1024):.2f} MB)" if member.size > 0 else ""
                print(f"{i:3d}. [文件] {member.name}{size_info}")
        
        # 提取文件
        print(f"\n正在解压到 {extract_to}...")
        tar.extractall(path=extract_to)
        print("解压完成!")
        
        # 统计信息
        print("\n" + "="*80)
        print("统计信息:")
        print(f"总文件数: {len(file_list)}")
        print(f"总目录数: {len(dir_list)}")
        
        total_size = sum(f["size"] for f in file_list)
        print(f"总文件大小: {total_size} 字节 ({total_size/(1024*1024):.2f} MB)")
        
        # 保存文件列表
        output_file = "/tmp/redis_inspection_contents.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump({
                "source_file": tar_gz_path,
                "file_size_bytes": file_size,
                "total_items": len(members),
                "directories": dir_list,
                "files": file_list,
                "extract_path": extract_to
            }, f, indent=2, ensure_ascii=False)
        
        print(f"\n详细信息已保存到: {output_file}")
        
except Exception as e:
    print(f"错误: {str(e)}")
    import traceback
    traceback.print_exc()