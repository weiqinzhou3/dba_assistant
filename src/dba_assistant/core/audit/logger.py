"""Compatibility wrapper for the repository audit recorder."""

from dba_assistant.core.observability.audit import AuditRecorder
from dba_assistant.core.observability.bootstrap import get_audit_recorder

__all__ = ["AuditRecorder", "get_audit_recorder"]
