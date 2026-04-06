from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from dba_assistant.application.request_models import RdbOverrides
from dba_assistant.capabilities.redis_rdb_analysis.types import EffectiveProfile

_PROFILE_DIR = Path(__file__).resolve().parent / "profiles"
_DEFAULT_TOP_N = {
    "prefix_top": 100,
    "focused_prefix_top_keys": 100,
    "top_big_keys": 100,
    "string_big_keys": 100,
    "list_big_keys": 100,
    "hash_big_keys": 100,
    "set_big_keys": 100,
    "zset_big_keys": 100,
    "stream_big_keys": 100,
    "other_big_keys": 100,
}


def available_profile_names() -> list[str]:
    return sorted(path.stem for path in _PROFILE_DIR.glob("*.yaml"))


def resolve_profile(profile_name: str, overrides: RdbOverrides) -> EffectiveProfile:
    profile_data = _load_profile(profile_name)

    sections = tuple(_as_str_list(profile_data.get("sections")))
    focus_prefixes = tuple(_as_str_list(profile_data.get("focus_prefixes", [])))
    top_n = dict(_DEFAULT_TOP_N)
    top_n.update(_as_int_mapping(profile_data.get("top_n", {})))
    top_n.update(overrides.top_n)
    effective_focus_prefixes = overrides.focus_prefixes or focus_prefixes

    return EffectiveProfile(
        name=str(profile_data.get("name", profile_name)).lower(),
        sections=sections,
        focus_prefixes=effective_focus_prefixes,
        focus_only=overrides.focus_only,
        top_n=top_n,
    )


def _load_profile(profile_name: str) -> dict[str, Any]:
    normalized_name = profile_name.strip().lower()
    path = _PROFILE_DIR / f"{normalized_name}.yaml"
    if not path.exists():
        available = ", ".join(available_profile_names())
        raise ValueError(f"Unknown profile '{profile_name}'. Available profiles: {available}")

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Profile file {path} must contain a mapping.")
    return data
def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise ValueError("Profile field must be a list of strings.")
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
    for key, raw_value in value.items():
        if not isinstance(key, str):
            raise ValueError("Profile top_n keys must be strings.")
        if not isinstance(raw_value, int):
            raise ValueError("Profile top_n values must be integers.")
        mapping[key] = raw_value
    return mapping
