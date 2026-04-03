from dba_assistant.interface.hitl import AutoApproveHandler, CliApprovalHandler
from dba_assistant.interface.types import ApprovalRequest, ApprovalStatus


def test_auto_approve_handler_approves_by_default() -> None:
    handler = AutoApproveHandler()
    req = ApprovalRequest(action="test", message="approve this?")
    resp = handler.request_approval(req)
    assert resp.status is ApprovalStatus.APPROVED
    assert resp.action == "test"


def test_auto_approve_handler_denies_when_configured() -> None:
    handler = AutoApproveHandler(approve=False)
    req = ApprovalRequest(action="test", message="approve this?")
    resp = handler.request_approval(req)
    assert resp.status is ApprovalStatus.DENIED


def test_cli_approval_handler_approves_on_y(monkeypatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _: "y")
    handler = CliApprovalHandler()
    req = ApprovalRequest(action="fetch", message="Fetch RDB?", details={"host": "redis.example"})
    resp = handler.request_approval(req)
    assert resp.status is ApprovalStatus.APPROVED
    assert resp.action == "fetch"


def test_cli_approval_handler_denies_on_n(monkeypatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _: "n")
    handler = CliApprovalHandler()
    req = ApprovalRequest(action="fetch", message="Fetch RDB?")
    resp = handler.request_approval(req)
    assert resp.status is ApprovalStatus.DENIED


def test_cli_approval_handler_denies_on_empty(monkeypatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _: "")
    handler = CliApprovalHandler()
    req = ApprovalRequest(action="fetch", message="Fetch RDB?")
    resp = handler.request_approval(req)
    assert resp.status is ApprovalStatus.DENIED
