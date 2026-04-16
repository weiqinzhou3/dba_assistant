from __future__ import annotations

import re
from typing import Any

from dba_assistant.interface.hitl import HumanApprovalHandler
from dba_assistant.orchestrator.tool_helpers import named_tool

_MYSQL_CONFIG_KEYWORDS = frozenset({"mysql", "数据库", "database", "staging"})
_MYSQL_REFUSAL_PATTERNS = [
    re.compile(r"不[要用需].*mysql", re.IGNORECASE),
    re.compile(r"no\s*mysql", re.IGNORECASE),
    re.compile(r"直接分析"),
    re.compile(r"不[要用需].*staging", re.IGNORECASE),
    re.compile(r"skip\s*mysql", re.IGNORECASE),
    re.compile(r"without\s*mysql", re.IGNORECASE),
    re.compile(r"不[要用需].*数据库"),
    re.compile(r"just\s+analyze", re.IGNORECASE),
]


def _is_mysql_related_question(question: str) -> bool:
    lower = question.lower()
    return any(token in lower for token in _MYSQL_CONFIG_KEYWORDS)


def _is_mysql_refusal(text: str) -> bool:
    return any(pattern.search(text) for pattern in _MYSQL_REFUSAL_PATTERNS)


def make_ask_user_for_config_tool(
    approval_handler: HumanApprovalHandler,
    *,
    rdb_session_state: dict[str, Any] | None = None,
):
    state = rdb_session_state if rdb_session_state is not None else {}

    def ask_user_for_config(question: str, secure: bool = False) -> str:
        # Block MySQL-related questions when the user already declined staging.
        if state.get("mysql_staging_refused") and _is_mysql_related_question(question):
            return (
                "MySQL staging was declined for this session. "
                "Do not ask for MySQL configuration. "
                "Use analyze_local_rdb_stream for direct analysis."
            )

        response = approval_handler.collect_input(question, secure=secure)

        # Detect MySQL refusal in user response and latch the flag.
        if state.get("large_rdb_detected") and _is_mysql_refusal(response):
            state["mysql_staging_refused"] = True

        return response

    return named_tool(
        ask_user_for_config,
        "ask_user_for_config",
        (
            "Ask the user for missing runtime configuration. "
            "Use this if you need information like MySQL host, user, or password "
            "before calling a tool. Parameters: question, secure. "
            "Do NOT use this to ask about MySQL after the user has declined staging."
        ),
    )
