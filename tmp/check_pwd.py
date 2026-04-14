#!/usr/bin/env python3
import os

print(f"当前工作目录: {os.getcwd()}")
print(f"文件绝对路径: {os.path.abspath('/references/legacy-workflows/redis-inspection-report/redis_info.tar.gz')}")
print(f"文件是否存在: {os.path.exists('/references/legacy-workflows/redis-inspection-report/redis_info.tar.gz')}")

# 尝试相对路径
print(f"\n尝试相对路径:")
print(f"../legacy-workflows/redis-inspection-report/redis_info.tar.gz 是否存在: {os.path.exists('../legacy-workflows/redis-inspection-report/redis_info.tar.gz')}")
print(f"./references/legacy-workflows/redis-inspection-report/redis_info.tar.gz 是否存在: {os.path.exists('./references/legacy-workflows/redis-inspection-report/redis_info.tar.gz')}")