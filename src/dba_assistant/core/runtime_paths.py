from __future__ import annotations

from pathlib import Path
import tempfile


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_AGENT_WORKSPACE_ROOT = REPO_ROOT / "outputs" / "agent_fs"
DEFAULT_ARTIFACT_DIR = DEFAULT_AGENT_WORKSPACE_ROOT / "artifacts"
DEFAULT_EVIDENCE_DIR = DEFAULT_AGENT_WORKSPACE_ROOT / "evidence"
DEFAULT_TEMP_DIR = DEFAULT_AGENT_WORKSPACE_ROOT / "tmp"


def ensure_directory(path: Path) -> Path:
    resolved = Path(path).expanduser()
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def make_runtime_work_dir(base_dir: Path | None, *, prefix: str) -> Path:
    base = ensure_directory(base_dir or DEFAULT_TEMP_DIR)
    return Path(tempfile.mkdtemp(prefix=prefix, dir=str(base)))
