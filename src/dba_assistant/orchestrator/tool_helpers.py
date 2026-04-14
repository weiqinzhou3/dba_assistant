from __future__ import annotations

from typing import Any


def named_tool(func: Any, name: str, description: str) -> Any:
    func.__name__ = name
    func.__doc__ = description
    return func


def human_readable_size(size: int) -> str:
    value = float(size)
    for unit in ["B", "KB", "MB", "GB"]:
        if value < 1024:
            return f"{value:.2f} {unit}"
        value /= 1024
    return f"{value:.2f} TB"
