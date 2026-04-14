#!/usr/bin/env python3
import tarfile
import os

# 源文件路径
tar_gz_path = "/references/legacy-workflows/redis-inspection-report/redis_info.tar.gz"

print(f"正在检查文件: {tar_gz_path}")

# 检查文件是否存在
if not os.path.exists(tar_gz_path):
    print(f"错误: 文件不存在")
    exit(1)

# 获取文件大小
file_size = os.path.getsize(tar_gz_path)
print(f"文件大小: {file_size} 字节 ({file_size/(1024*1024):.2f} MB)")

# 打开tar.gz文件并列出内容
try:
    print("\n正在读取压缩包内容...")
    with tarfile.open(tar_gz_path, "r:gz") as tar:
        # 获取所有成员
        members = tar.getmembers()
        print(f"压缩包中包含 {len(members)} 个文件/目录")
        
        print("\n完整的目录结构:")
        print("=" * 80)
        
        # 按目录组织文件
        dir_structure = {}
        
        for member in members:
            path_parts = member.name.split('/')
            
            # 构建目录树
            current = dir_structure
            for i, part in enumerate(path_parts):
                if i == len(path_parts) - 1:
                    # 最后一个部分是文件
                    if member.isdir():
                        current[part] = {"type": "directory", "contents": {}}
                    else:
                        current[part] = {
                            "type": "file", 
                            "size": member.size,
                            "size_mb": f"{member.size/(1024*1024):.2f} MB" if member.size > 0 else "0 MB"
                        }
                else:
                    # 中间目录
                    if part not in current:
                        current[part] = {"type": "directory", "contents": {}}
                    current = current[part]["contents"]
        
        # 打印目录结构
        def print_tree(node, indent=0, prefix=""):
            items = list(node.items())
            items.sort(key=lambda x: (0 if isinstance(x[1], dict) and "type" in x[1] and x[1]["type"] == "directory" else 1, x[0]))
            
            for i, (name, value) in enumerate(items):
                is_last = i == len(items) - 1
                current_prefix = "└── " if is_last else "├── "
                
                if isinstance(value, dict) and "type" in value:
                    if value["type"] == "directory":
                        print(f"{prefix}{current_prefix}{name}/")
                        new_prefix = prefix + ("    " if is_last else "│   ")
                        print_tree(value["contents"], indent + 1, new_prefix)
                    else:
                        size_info = f" ({value['size_mb']})" if value["size"] > 0 else ""
                        print(f"{prefix}{current_prefix}{name}{size_info}")
        
        print_tree(dir_structure)
        
        # 统计信息
        print("\n" + "="*80)
        print("统计信息:")
        
        dir_count = sum(1 for m in members if m.isdir())
        file_count = len(members) - dir_count
        total_size = sum(m.size for m in members if not m.isdir())
        
        print(f"总项目数: {len(members)}")
        print(f"目录数: {dir_count}")
        print(f"文件数: {file_count}")
        print(f"总文件大小: {total_size} 字节 ({total_size/(1024*1024):.2f} MB)")
        
        # 列出所有文件
        print("\n" + "="*80)
        print("详细文件列表:")
        
        for i, member in enumerate(members, 1):
            if not member.isdir():
                size_info = f" ({member.size/(1024*1024):.2f} MB)" if member.size > 0 else ""
                print(f"{i:3d}. {member.name}{size_info}")
        
except Exception as e:
    print(f"错误: {str(e)}")
    import traceback
    traceback.print_exc()