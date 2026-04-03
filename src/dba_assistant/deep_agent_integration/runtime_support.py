from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from deepagents.backends import FilesystemBackend


REPO_ROOT = Path(__file__).resolve().parents[3]
MEMORY_SOURCES = ("/AGENTS.md",)


def build_runtime_backend() -> FilesystemBackend:
    return FilesystemBackend(root_dir=REPO_ROOT, virtual_mode=True)


def get_memory_sources() -> list[str]:
    return list(MEMORY_SOURCES)


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
