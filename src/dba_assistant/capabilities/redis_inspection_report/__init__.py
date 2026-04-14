"""Redis inspection report capability."""

from dba_assistant.capabilities.redis_inspection_report.analyzer import analyze_inspection_dataset
from dba_assistant.capabilities.redis_inspection_report.service import (
    analyze_offline_inspection,
    analyze_remote_inspection,
)

__all__ = [
    "analyze_inspection_dataset",
    "analyze_offline_inspection",
    "analyze_remote_inspection",
]
