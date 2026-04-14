#!/bin/bash

TAR_FILE="/references/legacy-workflows/redis-inspection-report/redis_info.tar.gz"
EXTRACT_DIR="/tmp/redis_info_extracted"

echo "正在解压文件: $TAR_FILE"
echo "解压目录: $EXTRACT_DIR"

# 创建解压目录
mkdir -p "$EXTRACT_DIR"

# 解压文件
if tar -xzf "$TAR_FILE" -C "$EXTRACT_DIR"; then
    echo "解压成功!"
    echo ""
    echo "解压后的文件结构:"
    echo "=================="
    find "$EXTRACT_DIR" -type f | sort
    echo ""
    echo "目录结构:"
    echo "=========="
    find "$EXTRACT_DIR" -type d | sort
else
    echo "解压失败!"
    exit 1
fi