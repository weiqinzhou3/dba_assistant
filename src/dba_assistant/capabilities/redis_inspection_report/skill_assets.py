from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml


def load_log_issue_schema() -> dict[str, Any]:
    return _load_json_asset("log_issue_schema.json")


def load_table_schemas() -> dict[str, Any]:
    data = yaml.safe_load(_asset_path("table_schemas.yaml").read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def load_report_outline() -> tuple[str, ...]:
    titles: list[str] = []
    for line in _asset_path("report_outline.md").read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or not stripped[0].isdigit() or ". " not in stripped:
            continue
        _number, title = stripped.split(". ", 1)
        if title.strip():
            titles.append(title.strip())
    return tuple(titles)


def table_schema(name: str, *, fallback_title: str, fallback_columns: list[str]) -> tuple[str, list[str]]:
    schema = load_table_schemas().get(name)
    if not isinstance(schema, dict):
        return fallback_title, fallback_columns
    title = str(schema.get("title") or fallback_title)
    columns = schema.get("columns")
    if not isinstance(columns, list) or not all(isinstance(column, str) for column in columns):
        columns = fallback_columns
    return title, list(columns)


def outline_title(index: int, fallback: str) -> str:
    outline = load_report_outline()
    if 0 <= index < len(outline):
        return outline[index]
    return fallback


def _load_json_asset(name: str) -> dict[str, Any]:
    data = json.loads(_asset_path(name).read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _asset_path(name: str) -> Path:
    repository_root = Path(__file__).resolve().parents[4]
    return repository_root / "skills" / "redis-inspection-report" / "assets" / name


__all__ = [
    "load_log_issue_schema",
    "load_report_outline",
    "load_table_schemas",
    "outline_title",
    "table_schema",
]
