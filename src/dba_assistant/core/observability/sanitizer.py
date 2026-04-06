from __future__ import annotations

from collections.abc import Mapping, Sequence
import re
from typing import Any


REDACTED = "<redacted>"

_SENSITIVE_KEY_PATTERN = re.compile(
    r"(password|passwd|secret|token|api[_-]?key|authorization|credential|access[_-]?key)",
    re.IGNORECASE,
)
_KEY_VALUE_SECRET_PATTERN = re.compile(
    r"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key|redis_password|ssh_password|mysql_password)"
    r"\b\s*[:=]\s*([^\s,;]+)"
)


def sanitize_text(value: str, *, max_length: int | None = None) -> str:
    sanitized = _KEY_VALUE_SECRET_PATTERN.sub(r"\1=" + REDACTED, value)
    if max_length is not None and len(sanitized) > max_length:
        return sanitized[: max_length - 3] + "..."
    return sanitized


def sanitize_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        return sanitize_text(value)
    if isinstance(value, Mapping):
        return sanitize_mapping(value)
    if isinstance(value, tuple):
        return tuple(sanitize_value(item) for item in value)
    if isinstance(value, list):
        return [sanitize_value(item) for item in value]
    if isinstance(value, set):
        return sorted(sanitize_value(item) for item in value)
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [sanitize_value(item) for item in value]
    return value


def sanitize_mapping(data: Mapping[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in data.items():
        if _is_sensitive_key(str(key)):
            sanitized[str(key)] = REDACTED
            continue
        sanitized[str(key)] = sanitize_value(value)
    return sanitized


def summarize_prompt(prompt: str, *, max_length: int = 160) -> str:
    return sanitize_text(prompt.strip(), max_length=max_length)


def _is_sensitive_key(value: str) -> bool:
    return bool(_SENSITIVE_KEY_PATTERN.search(value))
