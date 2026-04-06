from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from typing import Any

from dba_assistant.core.observability.sanitizer import sanitize_value


_RESERVED_ATTRS = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "message",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
}


class SanitizingFilter(logging.Filter):
    def __init__(self, execution_lookup) -> None:
        super().__init__()
        self._execution_lookup = execution_lookup

    def filter(self, record: logging.LogRecord) -> bool:
        if record.args:
            try:
                formatted_message = record.msg % record.args
            except Exception:
                record.args = sanitize_value(record.args)
            else:
                record.msg = sanitize_value(formatted_message)
                record.args = ()
        else:
            record.msg = sanitize_value(record.msg)
        for key, value in list(record.__dict__.items()):
            if key in _RESERVED_ATTRS:
                continue
            record.__dict__[key] = sanitize_value(value)

        session = self._execution_lookup()
        if session is not None:
            record.execution_id = session.execution_id
            record.interface_surface = session.interface_surface.value
        else:
            record.execution_id = None
            record.interface_surface = None
        return True


class JsonlFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "execution_id": getattr(record, "execution_id", None),
            "interface_surface": getattr(record, "interface_surface", None),
        }

        event_name = getattr(record, "event_name", None)
        if event_name is not None:
            payload["event_name"] = event_name

        for key, value in record.__dict__.items():
            if key in _RESERVED_ATTRS or key in payload or key == "event_name":
                continue
            payload[key] = value

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False, sort_keys=False)
