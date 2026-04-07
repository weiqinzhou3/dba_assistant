#!/usr/bin/env bash
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
VENV_DIR=${VENV_DIR:-"$ROOT_DIR/.venv"}
VENV_PYTHON="$VENV_DIR/bin/python"

if [ ! -x "$VENV_PYTHON" ]; then
  printf 'run_cli error: %s\n' "virtual environment missing. Run ./scripts/bootstrap.sh first." >&2
  exit 1
fi

if ! "$VENV_PYTHON" -c "import dba_assistant" >/dev/null 2>&1; then
  printf 'run_cli error: %s\n' "current .venv cannot import dba_assistant. Run ./scripts/bootstrap.sh or ./scripts/bootstrap.sh --recreate." >&2
  exit 1
fi

exec "$VENV_PYTHON" -m dba_assistant.cli "$@"
