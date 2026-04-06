from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


# --- Canonical route names (Phase 3.1) ---
DATABASE_BACKED_ANALYSIS = "database_backed_analysis"
PREPARSED_DATASET_ANALYSIS = "preparsed_dataset_analysis"
DIRECT_RDB_ANALYSIS = "direct_rdb_analysis"

# --- Legacy aliases (kept for backward compatibility) ---
LEGACY_SQL_PIPELINE_ROUTE_NAME = DATABASE_BACKED_ANALYSIS
PRECOMPUTED_DATASET_ROUTE_NAME = PREPARSED_DATASET_ANALYSIS
DIRECT_MEMORY_ANALYSIS_ROUTE_NAME = DIRECT_RDB_ANALYSIS

# --- Normalization maps ---
_ROUTE_ALIAS_MAP: dict[str, str] = {
    "3a": DATABASE_BACKED_ANALYSIS,
    "legacy_sql_pipeline": DATABASE_BACKED_ANALYSIS,
    "3b": PREPARSED_DATASET_ANALYSIS,
    "precomputed_dataset": PREPARSED_DATASET_ANALYSIS,
    "3c": DIRECT_RDB_ANALYSIS,
    "direct_memory_analysis": DIRECT_RDB_ANALYSIS,
}

ROUTE_NAME_BY_PHASE_LABEL = {
    "3a": DATABASE_BACKED_ANALYSIS,
    "3b": PREPARSED_DATASET_ANALYSIS,
    "3c": DIRECT_RDB_ANALYSIS,
}
PHASE_LABEL_BY_ROUTE_NAME = {
    DATABASE_BACKED_ANALYSIS: "3a",
    PREPARSED_DATASET_ANALYSIS: "3b",
    DIRECT_RDB_ANALYSIS: "3c",
}


class InputSourceKind(str, Enum):
    LOCAL_RDB = "local_rdb"
    REMOTE_REDIS = "remote_redis"
    PRECOMPUTED = "precomputed"
    PREPARSED_MYSQL = "preparsed_mysql"


class AnalysisStatus(str, Enum):
    READY = "ready"
    CONFIRMATION_REQUIRED = "confirmation_required"


@dataclass(frozen=True)
class SampleInput:
    source: Path | str
    kind: InputSourceKind
    label: str | None = None


@dataclass(frozen=True)
class KeyRecord:
    sample_id: str
    key_name: str
    key_type: str
    size_bytes: int
    has_expiration: bool
    ttl_seconds: int | None
    prefix_segments: tuple[str, ...]


@dataclass(frozen=True)
class NormalizedRdbDataset:
    samples: list[SampleInput]
    records: list[KeyRecord]


@dataclass(frozen=True)
class EffectiveProfile:
    name: str
    sections: tuple[str, ...]
    focus_prefixes: tuple[str, ...] = ()
    top_n: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class RdbAnalysisRequest:
    prompt: str
    inputs: list[SampleInput]
    profile_name: str = "generic"
    report_language: str = "zh-CN"
    path_mode: str = "auto"
    merge_multiple_inputs: bool = True
    profile_overrides: dict[str, object] = field(default_factory=dict)
    mysql_table: str | None = None
    mysql_query: str | None = None


@dataclass(frozen=True)
class ConfirmationRequest:
    status: AnalysisStatus
    message: str
    required_action: str


def normalize_route_name(route_name: str) -> str:
    """Normalize any legacy or shorthand route name to its canonical form."""
    return _ROUTE_ALIAS_MAP.get(route_name, route_name)


def phase_label_for_route_name(route_name: str) -> str | None:
    """Return the phase label (3a/3b/3c) for a canonical route name."""
    canonical = normalize_route_name(route_name)
    return PHASE_LABEL_BY_ROUTE_NAME.get(canonical)
