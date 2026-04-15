from pathlib import Path

from dba_assistant.deep_agent_integration.config import FilesystemBackendConfig
from dba_assistant.deep_agent_integration.runtime_support import build_runtime_backend


def test_build_runtime_backend_uses_configured_filesystem_root_and_virtual_mode(tmp_path: Path) -> None:
    root = tmp_path / "agent-root"

    backend = build_runtime_backend(
        FilesystemBackendConfig(
            kind="filesystem",
            root_dir=root,
            virtual_mode=False,
        )
    )

    assert backend.cwd == root
    assert backend.virtual_mode is False
    assert root.exists()
