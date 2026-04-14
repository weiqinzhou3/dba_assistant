#!/usr/bin/env python3
import subprocess
import sys

# 直接运行分析脚本
result = subprocess.run([sys.executable, "/tmp/direct_extract.py"], 
                       capture_output=True, text=True)

print(result.stdout)
if result.stderr:
    print("错误输出:", result.stderr)