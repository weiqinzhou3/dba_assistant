from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from dba_assistant.core.observability.audit import AuditRecorder
from dba_assistant.core.observability.logging import JsonlFormatter, SanitizingFilter
from dba_assistant.deep_agent_integration.config import ObservabilityConfig


_STATE: dict[str, Any] = {
    "signature": None,
    "logger": None,
    "handlers": [],
    "audit_recorder": None,
}


def bootstrap_observability(config: ObservabilityConfig) -> None:
    signature = (
        config.enabled,
        config.level,
        config.console_enabled,
        str(config.log_dir),
        config.app_log_file,
        config.audit_log_file,
    )
    if _STATE["signature"] == signature:
        return

    reset_observability_state()

    logger = logging.getLogger("dba_assistant")
    logger.setLevel(_resolve_level(config.level))
    logger.propagate = False

    if not config.enabled:
        _STATE["signature"] = signature
        _STATE["logger"] = logger
        _STATE["handlers"] = []
        _STATE["audit_recorder"] = None
        return

    config.log_dir.mkdir(parents=True, exist_ok=True)

    from dba_assistant.core.observability.context import get_current_execution_session

    sanitize_filter = SanitizingFilter(get_current_execution_session)
    handlers: list[logging.Handler] = []

    if config.console_enabled:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(_resolve_level(config.level))
        console_handler.addFilter(sanitize_filter)
        console_handler.setFormatter(
            logging.Formatter("%(levelname)s %(name)s %(message)s")
        )
        logger.addHandler(console_handler)
        handlers.append(console_handler)

    app_handler = logging.FileHandler(config.app_log_path, encoding="utf-8")
    app_handler.setLevel(_resolve_level(config.level))
    app_handler.addFilter(sanitize_filter)
    app_handler.setFormatter(JsonlFormatter())
    logger.addHandler(app_handler)
    handlers.append(app_handler)

    audit_recorder = AuditRecorder(path=config.audit_log_path, enabled=config.enabled)

    _STATE["signature"] = signature
    _STATE["logger"] = logger
    _STATE["handlers"] = handlers
    _STATE["audit_recorder"] = audit_recorder


def get_audit_recorder() -> AuditRecorder | None:
    recorder = _STATE.get("audit_recorder")
    if recorder is None:
        return None
    return recorder


def reset_observability_state() -> None:
    logger = _STATE.get("logger")
    handlers = list(_STATE.get("handlers") or [])
    if logger is not None:
        for handler in handlers:
            logger.removeHandler(handler)
            handler.close()
    _STATE["signature"] = None
    _STATE["logger"] = None
    _STATE["handlers"] = []
    _STATE["audit_recorder"] = None


def _resolve_level(level_name: str) -> int:
    return int(getattr(logging, level_name.upper(), logging.INFO))
