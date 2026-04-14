#!/usr/bin/env python3
import tarfile
import os
import sys

def extract_tar_gz(tar_path, extract_to):
    """解压tar.gz文件"""
    try:
        # 检查文件是否存在
        if not os.path.exists(tar_path):
            print(f"错误: 文件不存在 - {tar_path}")
            return False
        
        # 获取文件大小
        file_size = os.path.getsize(tar_path)
        print(f"文件: {tar_path}")
        print(f"大小: {file_size} 字节 ({file_size/1024:.2f} KB)")
        
        # 创建解压目录
        os.makedirs(extract_to, exist_ok=True)
        
        # 解压文件
        print(f"解压到: {extract_to}")
        print("正在解压...")
        
        with tarfile.open(tar_path, 'r:gz') as tar:
            # 获取所有成员
            members = tar.getmembers()
            print(f"包含 {len(members)} 个文件/目录")
            
            # 解压所有文件
            tar.extractall(path=extract_to)
            
            print("解压完成!")
            return True
            
    except tarfile.ReadError as e:
        print(f"tar文件读取错误: {e}")
        return False
    except Exception as e:
        print(f"解压过程中发生错误: {e}")
        return False

def list_extracted_contents(extract_dir):
    """列出解压后的内容"""
    print("\n" + "="*60)
    print("解压后的内容结构")
    print("="*60)
    
    for root, dirs, files in os.walk(extract_dir):
        level = root.replace(extract_dir, '').count(os.sep)
        indent = ' ' * 2 * level
        print(f"{indent}{os.path.basename(root)}/")
        subindent = ' ' * 2 * (level + 1)
        for file in files:
            filepath = os.path.join(root, file)
            try:
                size = os.path.getsize(filepath)
                print(f"{subindent}{file} ({size} 字节)")
            except:
                print(f"{subindent}{file}")

if __name__ == "__main__":
    tar_file = "/references/legacy-workflows/redis-inspection-report/redis_info.tar.gz"
    extract_dir = "/tmp/redis_info_extracted"
    
    if extract_tar_gz(tar_file, extract_dir):
        list_extracted_contents(extract_dir)
    else:
        print("解压失败")