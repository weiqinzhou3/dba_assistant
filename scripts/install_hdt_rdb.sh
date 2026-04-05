#!/bin/sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
BIN_DIR="${ROOT_DIR}/.tools/bin"
VERSION="${DBA_ASSISTANT_HDT_RDB_VERSION:-latest}"

if ! command -v go >/dev/null 2>&1; then
  echo "go is required to install github.com/hdt3213/rdb" >&2
  exit 1
fi

mkdir -p "${BIN_DIR}"

echo "Installing github.com/hdt3213/rdb@${VERSION} into ${BIN_DIR}"
GOBIN="${BIN_DIR}" go install "github.com/hdt3213/rdb@${VERSION}"

echo "Installed: ${BIN_DIR}/rdb"
