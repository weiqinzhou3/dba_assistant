"""Collectors for the Redis inspection report skill."""

from dba_assistant.capabilities.redis_inspection_report.collectors.offline_evidence_collector import (
    RedisInspectionOfflineCollector,
    RedisInspectionOfflineInput,
)
from dba_assistant.capabilities.redis_inspection_report.collectors.remote_redis_collector import (
    RedisInspectionRemoteCollector,
    RedisInspectionRemoteInput,
)

__all__ = [
    "RedisInspectionOfflineCollector",
    "RedisInspectionOfflineInput",
    "RedisInspectionRemoteCollector",
    "RedisInspectionRemoteInput",
]
