from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeInputs:
    redis_host: str | None = None
    redis_port: int = 6379
    redis_db: int = 0
    output_mode: str = "summary"


@dataclass(frozen=True)
class Secrets:
    redis_password: str | None = None


@dataclass(frozen=True)
class NormalizedRequest:
    raw_prompt: str
    prompt: str
    runtime_inputs: RuntimeInputs
    secrets: Secrets
