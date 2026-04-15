from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml


def skill_package_dir(skill_name: str) -> Path:
    root = Path(__file__).resolve().parents[3]
    path = root / "skills" / skill_name
    if not path.exists():
        raise FileNotFoundError(f"Unknown skill package: {skill_name}")
    return path


def load_skill_json_asset(skill_name: str, relative_path: str) -> dict[str, Any]:
    data = json.loads(load_skill_text_asset(skill_name, relative_path))
    return data if isinstance(data, dict) else {}


def load_skill_yaml_asset(skill_name: str, relative_path: str) -> dict[str, Any]:
    data = yaml.safe_load(load_skill_text_asset(skill_name, relative_path))
    return data if isinstance(data, dict) else {}


def load_skill_text_asset(skill_name: str, relative_path: str) -> str:
    path = skill_package_dir(skill_name) / relative_path
    return path.read_text(encoding="utf-8")


def load_numbered_outline_titles(skill_name: str, relative_path: str) -> tuple[str, ...]:
    titles: list[str] = []
    for line in load_skill_text_asset(skill_name, relative_path).splitlines():
        stripped = line.strip()
        if not stripped or not stripped[0].isdigit() or ". " not in stripped:
            continue
        _number, title = stripped.split(". ", 1)
        if title.strip():
            titles.append(title.strip())
    return tuple(titles)


__all__ = [
    "load_numbered_outline_titles",
    "load_skill_json_asset",
    "load_skill_text_asset",
    "load_skill_yaml_asset",
    "skill_package_dir",
]
