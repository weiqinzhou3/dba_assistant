#!/usr/bin/env bash
set -eu

log() {
  printf '%s\n' "$*"
}

die() {
  printf 'bootstrap error: %s\n' "$*" >&2
  exit 1
}

ROOT_DIR=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
VENV_DIR=${VENV_DIR:-"$ROOT_DIR/.venv"}
PYTHON_BIN=${PYTHON_BIN:-python3}
INSTALL_TARGET=${INSTALL_TARGET:-"."}
SKIP_PIP_UPGRADE=${SKIP_PIP_UPGRADE:-0}
RECREATE=0

while [ $# -gt 0 ]; do
  case "$1" in
    --recreate)
      RECREATE=1
      ;;
    --runtime-only)
      INSTALL_TARGET="."
      ;;
    --dev)
      INSTALL_TARGET=".[dev]"
      ;;
    --skip-pip-upgrade)
      SKIP_PIP_UPGRADE=1
      ;;
    *)
      die "unknown option: $1"
      ;;
  esac
  shift
done

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  die "python interpreter not found: $PYTHON_BIN"
fi

if [ "$RECREATE" -eq 1 ] && [ -d "$VENV_DIR" ]; then
  log "Removing existing virtual environment: $VENV_DIR"
  rm -rf "$VENV_DIR"
fi

if [ ! -d "$VENV_DIR" ]; then
  log "Creating virtual environment: $VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR" || die "failed to create virtual environment"
fi

VENV_PYTHON="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"
VENV_CLI="$VENV_DIR/bin/dba-assistant"

[ -x "$VENV_PYTHON" ] || die "virtual environment python is missing: $VENV_PYTHON"
[ -x "$VENV_PIP" ] || die "virtual environment pip is missing: $VENV_PIP"

if [ "$SKIP_PIP_UPGRADE" -ne 1 ]; then
  log "Upgrading pip/setuptools/wheel"
  "$VENV_PYTHON" -m pip install --upgrade pip setuptools wheel || die "failed to upgrade pip/setuptools/wheel"
fi

log "Installing project into $VENV_DIR with target $INSTALL_TARGET"
(
  cd "$ROOT_DIR"
  "$VENV_PYTHON" -m pip install --no-build-isolation -e "$INSTALL_TARGET" || die "editable install failed"
)

repair_repo_src_pth() {
  SITE_PACKAGES=$("$VENV_PYTHON" - <<'PY'
import site

paths = [path for path in site.getsitepackages() if path.endswith("site-packages")]
if not paths:
    raise SystemExit("no site-packages directory found for current interpreter")
print(paths[0])
PY
)
  printf '%s\n' "$ROOT_DIR/src" > "$SITE_PACKAGES/dba_assistant_repo_src.pth"
}

if ! "$VENV_PYTHON" -c "import dba_assistant" >/dev/null 2>&1; then
  log "Editable install metadata exists but import still fails. Writing stable repo-src .pth repair."
  repair_repo_src_pth
fi

"$VENV_PYTHON" -c "import dba_assistant" >/dev/null 2>&1 || die "dba_assistant is still not importable after install"
[ -x "$VENV_CLI" ] || die "console script missing after install: $VENV_CLI"
"$VENV_CLI" --help >/dev/null 2>&1 || die "console script exists but --help failed"
"$VENV_PYTHON" "$ROOT_DIR/scripts/doctor.py" --expect-venv "$VENV_DIR" --strict || die "doctor check failed"

log "Bootstrap complete."
log "Use $VENV_CLI --help"
