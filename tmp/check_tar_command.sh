#!/bin/bash
echo "检查tar命令..."
which tar
echo -e "\n检查文件..."
ls -lh "/references/legacy-workflows/redis-inspection-report/redis_info.tar.gz"
echo -e "\n列出tar.gz内容..."
tar -tzf "/references/legacy-workflows/redis-inspection-report/redis_info.tar.gz" 2>/dev/null || echo "无法列出内容"