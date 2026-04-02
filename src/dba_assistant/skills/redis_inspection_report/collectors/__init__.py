"""Collectors for the Redis inspection report skill."""

from dba_assistant.skills.redis_inspection_report.collectors.remote_redis_collector import (
    RedisInspectionRemoteCollector,
    RedisInspectionRemoteInput,
)

__all__ = ["RedisInspectionRemoteCollector", "RedisInspectionRemoteInput"]
