"""Human-in-the-loop approval handlers."""
from __future__ import annotations

from typing import Protocol

from dba_assistant.core.observability import get_current_execution_session
from dba_assistant.core.observability.sanitizer import sanitize_mapping, sanitize_text
from dba_assistant.interface.types import ApprovalRequest, ApprovalResponse, ApprovalStatus


class HumanApprovalHandler(Protocol):
    """Protocol for HITL confirmation handlers.

    Implementations:
    - CliApprovalHandler  — interactive stdin prompt (CLI)
    - AutoApproveHandler  — testing / trusted-automation
    - (future) WebhookApprovalHandler — Web / API async callback
    """

    def request_approval(self, request: ApprovalRequest) -> ApprovalResponse: ...


class CliApprovalHandler:
    """CLI-based approval handler that prompts on stdin."""

    def request_approval(self, request: ApprovalRequest) -> ApprovalResponse:
        print(f"\n[Approval Required] {request.message}")
        if request.details:
            for key, value in request.details.items():
                print(f"  {key}: {value}")

        response = input("\nApprove? [y/N]: ").strip().lower()
        status = ApprovalStatus.APPROVED if response in ("y", "yes") else ApprovalStatus.DENIED
        return ApprovalResponse(status=status, action=request.action)


class AutoApproveHandler:
    """Auto-approve handler for testing and trusted automation."""

    def __init__(self, *, approve: bool = True, deny_reason: str | None = None) -> None:
        self._approve = approve
        self._deny_reason = deny_reason

    def request_approval(self, request: ApprovalRequest) -> ApprovalResponse:
        status = ApprovalStatus.APPROVED if self._approve else ApprovalStatus.DENIED
        return ApprovalResponse(
            status=status,
            action=request.action,
            reason=None if status is ApprovalStatus.APPROVED else self._deny_reason,
        )


class AuditedApprovalHandler:
    """Decorator that records approval lifecycle events as first-class audit entries."""

    def __init__(self, delegate: HumanApprovalHandler) -> None:
        self._delegate = delegate

    def request_approval(self, request: ApprovalRequest) -> ApprovalResponse:
        sanitized_request = ApprovalRequest(
            action=request.action,
            message=sanitize_text(request.message),
            details=sanitize_mapping(request.details),
        )

        session = get_current_execution_session()
        if session is not None:
            session.record_event(
                "approval_requested",
                action=sanitized_request.action,
                message=sanitized_request.message,
                details=sanitized_request.details,
            )

        response = self._delegate.request_approval(sanitized_request)
        sanitized_reason = None if response.reason is None else sanitize_text(response.reason)

        if session is not None:
            session.record_event(
                "approval_resolved",
                action=sanitized_request.action,
                approval_outcome=response.status.value,
                rejection_reason=sanitized_reason,
            )
            if response.status is ApprovalStatus.DENIED:
                session.mark_status("denied", detail=sanitized_reason or sanitized_request.action)

        return ApprovalResponse(
            status=response.status,
            action=response.action,
            reason=sanitized_reason,
        )
