"""Redis adaptor scaffold."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RedisConnectionConfig:
    host: str
    port: int
    db: int = 0
    username: str | None = None
    password: str | None = None
    socket_timeout: float = 5.0
