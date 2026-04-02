from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dba_assistant.adaptors.redis_adaptor import RedisAdaptor, RedisConnectionConfig
from dba_assistant.core.collector.remote_collector import RemoteCollector


DEFAULT_CONFIG_PATTERN = "maxmemory*"
ALLOWED_CONFIG_PATTERNS = frozenset({DEFAULT_CONFIG_PATTERN})
MAX_SLOWLOG_LENGTH = 5


@dataclass(frozen=True)
class RedisInspectionRemoteInput:
    connection: RedisConnectionConfig
    info_section: str | None = None
    config_pattern: str = DEFAULT_CONFIG_PATTERN
    slowlog_length: int = MAX_SLOWLOG_LENGTH

    def __post_init__(self) -> None:
        if self.config_pattern not in ALLOWED_CONFIG_PATTERNS:
            raise ValueError(
                f"config_pattern must be one of {sorted(ALLOWED_CONFIG_PATTERNS)} for Phase 2."
            )
        if not 1 <= self.slowlog_length <= MAX_SLOWLOG_LENGTH:
            raise ValueError(
                f"slowlog_length must be between 1 and {MAX_SLOWLOG_LENGTH} for Phase 2."
            )


class RedisInspectionRemoteCollector(RemoteCollector[RedisInspectionRemoteInput, dict[str, Any]]):
    def __init__(self, adaptor: RedisAdaptor | None = None) -> None:
        super().__init__(readonly=True)
        self.adaptor = adaptor or RedisAdaptor()

    def collect_readonly(self, collector_input: RedisInspectionRemoteInput) -> dict[str, Any]:
        connection = collector_input.connection
        return {
            "ping": self.adaptor.ping(connection),
            "info": self.adaptor.info(connection, section=collector_input.info_section),
            "config": self.adaptor.config_get(connection, pattern=collector_input.config_pattern),
            "slowlog": self.adaptor.slowlog_get(connection, length=collector_input.slowlog_length),
            "clients": self.adaptor.client_list(connection),
        }
