import subprocess
import sys

result = subprocess.run([sys.executable, "/tmp/extract_tar.py"], 
                       capture_output=True, text=True, encoding='utf-8')

print("标准输出:")
print(result.stdout)

if result.stderr:
    print("\n标准错误:")
    print(result.stderr)

print(f"\n返回码: {result.returncode}")