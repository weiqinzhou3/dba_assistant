from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class RuntimeInputs:
    redis_host: str | None = None
    redis_port: int = 6379
    redis_db: int = 0
    output_mode: str = "summary"
    input_paths: tuple[Path, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Secrets:
    redis_password: str | None = None


@dataclass(frozen=True)
class RdbOverrides:
    profile_name: str | None = None
    focus_prefixes: tuple[str, ...] = ()
    top_n: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class NormalizedRequest:
    raw_prompt: str
    prompt: str
    runtime_inputs: RuntimeInputs
    secrets: Secrets
    rdb_overrides: RdbOverrides = field(default_factory=RdbOverrides)
