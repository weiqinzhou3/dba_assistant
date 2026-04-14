#!/usr/bin/env python3
import tarfile
import os
import sys

def main():
    tar_path = "/references/legacy-workflows/redis-inspection-report/redis_info.tar.gz"
    extract_dir = "/tmp/redis_extracted"
    
    print("=" * 70)
    print("Redis Info Tar.gz 文件分析")
    print("=" * 70)
    
    # 1. 检查文件基本信息
    print("\n1. 文件基本信息:")
    print("-" * 40)
    
    if not os.path.exists(tar_path):
        print(f"错误: 文件不存在 - {tar_path}")
        return
    
    try:
        file_size = os.path.getsize(tar_path)
        print(f"路径: {tar_path}")
        print(f"大小: {file_size:,} 字节 ({file_size/1024:.1f} KB)")
        
        # 检查权限
        import stat
        st = os.stat(tar_path)
        print(f"权限: {oct(st.st_mode)[-3:]}")
        print(f"用户: {st.st_uid}")
        print(f"组  : {st.st_gid}")
        
    except Exception as e:
        print(f"获取文件信息时出错: {e}")
        return
    
    # 2. 尝试列出tar.gz内容（不解压）
    print("\n2. Tar.gz文件内容列表:")
    print("-" * 40)
    
    try:
        with tarfile.open(tar_path, 'r:gz') as tar:
            members = tar.getmembers()
            print(f"包含 {len(members)} 个项目:")
            
            for i, member in enumerate(members, 1):
                type_char = member.type
                type_desc = {
                    tarfile.REGTYPE: '文件',
                    tarfile.DIRTYPE: '目录',
                    tarfile.SYMTYPE: '符号链接',
                    tarfile.LNKTYPE: '硬链接'
                }.get(type_char, '其他')
                
                size_info = f"{member.size:,} 字节" if member.size else ""
                print(f"  {i:3d}. [{type_desc:4}] {member.name} {size_info}")
                
    except tarfile.ReadError as e:
        print(f"读取tar文件错误: {e}")
        print("文件可能已损坏或不是有效的tar.gz文件")
        return
    except Exception as e:
        print(f"列出内容时出错: {e}")
        return
    
    # 3. 尝试解压到临时目录
    print("\n3. 解压文件:")
    print("-" * 40)
    
    try:
        # 清理旧的解压目录
        import shutil
        if os.path.exists(extract_dir):
            shutil.rmtree(extract_dir)
        
        os.makedirs(extract_dir, exist_ok=True)
        
        with tarfile.open(tar_path, 'r:gz') as tar:
            tar.extractall(path=extract_dir)
            print(f"✓ 成功解压到: {extract_dir}")
            
    except Exception as e:
        print(f"✗ 解压失败: {e}")
        return
    
    # 4. 列出解压后的目录结构
    print("\n4. 解压后的目录结构:")
    print("-" * 40)
    
    def list_dir(path, indent=0):
        try:
            items = os.listdir(path)
            for item in sorted(items):
                item_path = os.path.join(path, item)
                prefix = "  " * indent + "├── "
                
                if os.path.isdir(item_path):
                    print(f"{prefix}{item}/")
                    list_dir(item_path, indent + 1)
                else:
                    size = os.path.getsize(item_path)
                    print(f"{prefix}{item} ({size:,} 字节)")
        except Exception as e:
            print(f"{'  ' * indent}└── [错误读取目录: {e}]")
    
    list_dir(extract_dir)
    
    # 5. 显示一些文件内容示例
    print("\n5. 文本文件内容示例:")
    print("-" * 40)
    
    def find_text_files(root_dir, max_files=3):
        text_files = []
        for root, dirs, files in os.walk(root_dir):
            for file in files:
                file_path = os.path.join(root, file)
                # 检查文件扩展名或尝试读取
                if file.endswith(('.txt', '.log', '.conf', '.json', '.yml', '.yaml', '.xml')):
                    text_files.append(file_path)
                elif file_size < 10240:  # 小于10KB的文件也尝试显示
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read(100)
                            if any(c.isprintable() for c in content):
                                text_files.append(file_path)
                    except:
                        pass
                
                if len(text_files) >= max_files:
                    return text_files
        return text_files
    
    text_files = find_text_files(extract_dir)
    for i, file_path in enumerate(text_files, 1):
        print(f"\n文件 {i}: {os.path.relpath(file_path, extract_dir)}")
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read(500)
                print(f"内容预览:\n{content[:200]}..." if len(content) > 200 else content)
        except Exception as e:
            print(f"读取失败: {e}")
    
    print("\n" + "=" * 70)
    print("分析完成")
    print("=" * 70)

if __name__ == "__main__":
    main()