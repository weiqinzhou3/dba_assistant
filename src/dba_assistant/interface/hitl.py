"""Human-in-the-loop approval handlers."""
from __future__ import annotations

from typing import Protocol

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

    def __init__(self, *, approve: bool = True) -> None:
        self._approve = approve

    def request_approval(self, request: ApprovalRequest) -> ApprovalResponse:
        status = ApprovalStatus.APPROVED if self._approve else ApprovalStatus.DENIED
        return ApprovalResponse(status=status, action=request.action)
