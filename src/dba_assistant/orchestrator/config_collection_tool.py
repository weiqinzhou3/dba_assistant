from __future__ import annotations

from dba_assistant.interface.hitl import HumanApprovalHandler
from dba_assistant.orchestrator.tool_helpers import named_tool


def make_ask_user_for_config_tool(approval_handler: HumanApprovalHandler):
    def ask_user_for_config(question: str, secure: bool = False) -> str:
        return approval_handler.collect_input(question, secure=secure)

    return named_tool(
        ask_user_for_config,
        "ask_user_for_config",
        (
            "Ask the user for missing runtime configuration. "
            "Use this if you need information like MySQL host, user, or password "
            "before calling a tool. Parameters: question, secure."
        ),
    )
