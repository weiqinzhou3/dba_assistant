from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dba_assistant.adaptors.redis_adaptor import RedisAdaptor, RedisConnectionConfig
from dba_assistant.core.collector.remote_collector import RemoteCollector


@dataclass(frozen=True)
class RedisInspectionRemoteInput:
    connection: RedisConnectionConfig
    info_section: str | None = None
    config_pattern: str = "*"
    slowlog_length: int = 10


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
