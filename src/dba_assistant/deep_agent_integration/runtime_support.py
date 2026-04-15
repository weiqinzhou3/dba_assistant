from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from deepagents.backends import FilesystemBackend
from langgraph.checkpoint.memory import InMemorySaver

from dba_assistant.deep_agent_integration.config import FilesystemBackendConfig
from dba_assistant.core.runtime_paths import REPO_ROOT, ensure_directory

MEMORY_SOURCES = ("/AGENTS.md",)
SKILL_SOURCES = ("/skills",)


def build_runtime_backend(config: FilesystemBackendConfig | None = None) -> FilesystemBackend:
    filesystem_config = config or FilesystemBackendConfig()
    if filesystem_config.kind != "filesystem":
        raise ValueError("Only filesystem backend is supported.")
    root_dir = ensure_directory(filesystem_config.root_dir)
    return FilesystemBackend(root_dir=root_dir, virtual_mode=filesystem_config.virtual_mode)


def get_memory_sources() -> list[str]:
    return list(MEMORY_SOURCES)


def get_skill_sources() -> list[str]:
    return list(SKILL_SOURCES)


def build_runtime_checkpointer() -> InMemorySaver:
    return InMemorySaver()


def extract_agent_output(result: Any) -> str:
    if isinstance(result, str):
        return result

    if isinstance(result, dict):
        messages = result.get("messages")
        if isinstance(messages, Sequence):
            for message in reversed(messages):
                text = _extract_message_text(message)
                if text:
                    return text

        for key in ("output", "response", "structured_response"):
            value = result.get(key)
            if value is not None:
                return str(value)

    text = _extract_message_text(result)
    if text:
        return text

    return str(result)


def _extract_message_text(message: Any) -> str:
    content = getattr(message, "content", None)
    if content is None and isinstance(message, dict):
        content = message.get("content")

    if isinstance(content, str):
        return content

    if isinstance(content, Sequence) and not isinstance(content, (str, bytes, bytearray)):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                if item.strip():
                    parts.append(item)
                continue
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            if isinstance(text, str) and text.strip():
                parts.append(text)
                continue
            inner_content = item.get("content")
            if isinstance(inner_content, str) and inner_content.strip():
                parts.append(inner_content)
        return "\n".join(parts).strip()

    return ""
