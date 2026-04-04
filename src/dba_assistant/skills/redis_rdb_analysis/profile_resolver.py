from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from dba_assistant.application.request_models import RdbOverrides
from dba_assistant.skills.redis_rdb_analysis.types import EffectiveProfile

_PROFILE_DIR = Path(__file__).resolve().parent / "profiles"
_DEFAULT_TOP_N = {
    "prefix_top": 20,
    "top_big_keys": 20,
    "list_big_keys": 10,
    "hash_big_keys": 10,
    "set_big_keys": 10,
}


def available_profile_names() -> list[str]:
    """Return sorted list of available profile names from profiles/*.yaml."""
    return sorted(p.stem for p in _PROFILE_DIR.glob("*.yaml"))


def resolve_profile(profile_name: str, overrides: RdbOverrides) -> EffectiveProfile:
    profile_data = _load_profile(profile_name)

    sections = tuple(_extract_sections(profile_data))
    base_focus_prefixes = tuple(_extract_focus_prefixes(profile_data))
    base_top_n = dict(_DEFAULT_TOP_N)
    base_top_n.update(_extract_top_n(profile_data))

    return EffectiveProfile(
        name=str(profile_data.get("name", profile_name)).lower(),
        sections=sections,
        focus_prefixes=_merge_unique(base_focus_prefixes, overrides.focus_prefixes),
        top_n={**base_top_n, **overrides.top_n},
    )


def _load_profile(profile_name: str) -> dict[str, Any]:
    normalized_name = profile_name.strip().lower()
    path = _PROFILE_DIR / f"{normalized_name}.yaml"
    if not path.exists():
        available = ", ".join(sorted(p.stem for p in _PROFILE_DIR.glob("*.yaml")))
        raise ValueError(f"Unknown profile '{profile_name}'. Available profiles: {available}")

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Profile file {path} must contain a mapping.")
    return data


def _extract_sections(data: dict[str, Any]) -> list[str]:
    if "sections" in data:
        return _as_str_list(data["sections"])
    report = data.get("report", {})
    if isinstance(report, dict) and "sections" in report:
        return _as_str_list(report["sections"])
    raise ValueError("Profile is missing sections.")


def _extract_focus_prefixes(data: dict[str, Any]) -> list[str]:
    if "focus_prefixes" in data:
        return _as_str_list(data["focus_prefixes"])
    analysis = data.get("analysis", {})
    if isinstance(analysis, dict) and "focus_prefixes" in analysis:
        return _as_str_list(analysis["focus_prefixes"])
    return []


def _extract_top_n(data: dict[str, Any]) -> dict[str, int]:
    if "top_n" in data:
        return _as_int_mapping(data["top_n"])
    analysis = data.get("analysis", {})
    if isinstance(analysis, dict) and "top_n" in analysis:
        return _as_int_mapping(analysis["top_n"])
    return {}


def _merge_unique(base: tuple[str, ...], overrides: tuple[str, ...]) -> tuple[str, ...]:
    merged: list[str] = []
    seen: set[str] = set()
    for value in (*base, *overrides):
        if value not in seen:
            seen.add(value)
            merged.append(value)
    return tuple(merged)


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise ValueError("Profile fields must be lists.")
    items: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError("Profile list entries must be strings.")
        items.append(item)
    return items


def _as_int_mapping(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        raise ValueError("Profile top_n must be a mapping.")
    mapping: dict[str, int] = {}
    for key, raw_count in value.items():
        if not isinstance(key, str):
            raise ValueError("Profile top_n keys must be strings.")
        if not isinstance(raw_count, int):
            raise ValueError("Profile top_n values must be integers.")
        mapping[key] = raw_count
    return mapping
