from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
import logging
from typing import Any

from dba_assistant.core.observability.context import get_current_execution_session


_PHASE_EVENT_HANDLER: ContextVar[Callable[[dict[str, Any]], None] | None] = ContextVar(
    "dba_assistant_rdb_phase_event_handler",
    default=None,
)


@contextmanager
def rdb_phase_event_handler(
    event_handler: Callable[[dict[str, Any]], None] | None,
) -> Iterator[None]:
    token: Token[Callable[[dict[str, Any]], None] | None] = _PHASE_EVENT_HANDLER.set(event_handler)
    try:
        yield
    finally:
        _PHASE_EVENT_HANDLER.reset(token)


def emit_rdb_phase(
    logger: logging.Logger,
    phase: str,
    *,
    tool_name: str = "analyze_local_rdb_stream",
    message: str = "rdb analysis phase",
    **payload: Any,
) -> None:
    clean_payload = {key: value for key, value in payload.items() if value is not None}
    logger.info(
        message,
        extra={
            "event_name": "redis_rdb_analysis_phase",
            "phase": phase,
            "tool_name": tool_name,
            **clean_payload,
        },
    )

    session = get_current_execution_session()
    if session is not None:
        session.record_event(
            "redis_rdb_analysis_phase",
            phase=phase,
            tool_name=tool_name,
            **clean_payload,
        )

    handler = _PHASE_EVENT_HANDLER.get()
    if handler is not None:
        handler(
            {
                "type": "tool_phase",
                "tool_name": tool_name,
                "phase": phase,
                **clean_payload,
            }
        )
