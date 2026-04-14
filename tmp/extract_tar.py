#!/usr/bin/env python3
import tarfile
import os
import sys
import json

def extract_and_list_tar_gz(tar_gz_path, extract_to="/tmp/redis_inspection_extract"):
    """解压tar.gz文件并列出内容"""
    
    # 创建提取目录
    os.makedirs(extract_to, exist_ok=True)
    
    # 检查文件是否存在
    if not os.path.exists(tar_gz_path):
        return {"error": f"文件不存在: {tar_gz_path}"}
    
    # 获取文件大小
    file_size = os.path.getsize(tar_gz_path)
    
    # 解压文件
    try:
        with tarfile.open(tar_gz_path, "r:gz") as tar:
            # 获取所有成员
            members = tar.getmembers()
            
            # 提取文件
            tar.extractall(path=extract_to)
            
            # 构建文件结构
            file_structure = {
                "source_file": tar_gz_path,
                "file_size_bytes": file_size,
                "file_size_mb": round(file_size / (1024 * 1024), 2),
                "total_files": len(members),
                "extract_path": extract_to,
                "files": []
            }
            
            # 收集文件信息
            for member in members:
                file_info = {
                    "name": member.name,
                    "type": "directory" if member.isdir() else "file",
                    "size_bytes": member.size if not member.isdir() else 0,
                    "size_mb": round(member.size / (1024 * 1024), 2) if not member.isdir() else 0,
                    "path": os.path.join(extract_to, member.name)
                }
                file_structure["files"].append(file_info)
            
            return file_structure
            
    except Exception as e:
        return {"error": f"解压失败: {str(e)}"}

def list_directory_structure(base_path, max_depth=3, current_depth=0):
    """递归列出目录结构"""
    if current_depth > max_depth:
        return []
    
    structure = []
    try:
        items = os.listdir(base_path)
        for item in sorted(items):
            item_path = os.path.join(base_path, item)
            rel_path = os.path.relpath(item_path, "/tmp/redis_inspection_extract")
            
            if os.path.isdir(item_path):
                structure.append({
                    "name": item,
                    "type": "directory",
                    "path": rel_path,
                    "children": list_directory_structure(item_path, max_depth, current_depth + 1)
                })
            else:
                size = os.path.getsize(item_path)
                structure.append({
                    "name": item,
                    "type": "file",
                    "path": rel_path,
                    "size_bytes": size,
                    "size_mb": round(size / (1024 * 1024), 2)
                })
    except Exception as e:
        structure.append({"error": str(e)})
    
    return structure

if __name__ == "__main__":
    tar_gz_path = "/references/legacy-workflows/redis-inspection-report/redis_info.tar.gz"
    extract_to = "/tmp/redis_inspection_extract"
    
    print("正在解压文件...")
    result = extract_and_list_tar_gz(tar_gz_path, extract_to)
    
    if "error" in result:
        print(f"错误: {result['error']}")
        sys.exit(1)
    
    print("\n" + "="*60)
    print("文件基本信息:")
    print("="*60)
    print(f"源文件: {result['source_file']}")
    print(f"文件大小: {result['file_size_mb']} MB ({result['file_size_bytes']} 字节)")
    print(f"包含文件总数: {result['total_files']}")
    print(f"解压目录: {result['extract_path']}")
    
    print("\n" + "="*60)
    print("文件列表:")
    print("="*60)
    for i, file_info in enumerate(result['files'], 1):
        file_type = "目录" if file_info['type'] == 'directory' else "文件"
        size_info = f"{file_info['size_mb']} MB" if file_info['size_mb'] > 0 else ""
        print(f"{i:3d}. [{file_type}] {file_info['name']} {size_info}")
    
    print("\n" + "="*60)
    print("目录结构:")
    print("="*60)
    
    # 获取目录结构
    dir_structure = list_directory_structure(extract_to)
    
    def print_structure(items, indent=0):
        for item in items:
            prefix = "  " * indent + "├── "
            if item['type'] == 'directory':
                print(f"{prefix}[目录] {item['name']}/")
                if 'children' in item:
                    print_structure(item['children'], indent + 1)
            else:
                size_info = f" ({item['size_mb']} MB)" if item['size_mb'] > 0 else ""
                print(f"{prefix}[文件] {item['name']}{size_info}")
    
    print_structure(dir_structure)
    
    # 保存结果到文件
    output_file = "/tmp/redis_inspection_structure.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            "extraction_result": result,
            "directory_structure": dir_structure
        }, f, indent=2, ensure_ascii=False)
    
    print(f"\n详细结构已保存到: {output_file}")