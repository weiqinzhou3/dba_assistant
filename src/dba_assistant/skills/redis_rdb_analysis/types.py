from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class InputSourceKind(str, Enum):
    LOCAL_RDB = "local_rdb"
    REMOTE_REDIS = "remote_redis"
    PRECOMPUTED = "precomputed"


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
    path_mode: str = "auto"
    merge_multiple_inputs: bool = True
    profile_overrides: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ConfirmationRequest:
    status: AnalysisStatus
    message: str
    required_action: str
