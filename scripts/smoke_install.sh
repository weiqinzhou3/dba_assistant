#!/usr/bin/env bash
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
PYTHON_BIN=${PYTHON_BIN:-python3}
SMOKE_VENV=${SMOKE_VENV:-"$ROOT_DIR/.tmp/install-smoke-venv"}
KEEP_SMOKE_VENV=${KEEP_SMOKE_VENV:-0}

cleanup() {
  if [ "$KEEP_SMOKE_VENV" -eq 0 ] && [ -d "$SMOKE_VENV" ]; then
    rm -rf "$SMOKE_VENV"
  fi
}

trap cleanup EXIT

rm -rf "$SMOKE_VENV"
mkdir -p "$(dirname "$SMOKE_VENV")"

VENV_DIR="$SMOKE_VENV" PYTHON_BIN="$PYTHON_BIN" "$ROOT_DIR/scripts/bootstrap.sh" "$@"
"$SMOKE_VENV/bin/python" -c "import dba_assistant; print(dba_assistant.__file__)"
"$SMOKE_VENV/bin/dba-assistant" --help >/dev/null
"$SMOKE_VENV/bin/python" "$ROOT_DIR/scripts/doctor.py" --expect-venv "$SMOKE_VENV" --strict

printf '%s\n' "install smoke test passed"
