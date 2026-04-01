"""Collector layer contracts and base implementations."""

from dba_assistant.core.collector.offline_collector import OfflineCollector
from dba_assistant.core.collector.remote_collector import RemoteCollector
from dba_assistant.core.collector.types import CollectedFile, ICollector, OfflineCollectorInput

__all__ = [
    "CollectedFile",
    "ICollector",
    "OfflineCollector",
    "OfflineCollectorInput",
    "RemoteCollector",
]
