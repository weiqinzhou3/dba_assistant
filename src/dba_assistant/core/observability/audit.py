from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from threading import Lock
from typing import Any

from dba_assistant.core.observability.sanitizer import sanitize_mapping, sanitize_value


@dataclass(frozen=True)
class AuditRecorder:
    path: Path
    enabled: bool = True

    def __post_init__(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)
        object.__setattr__(self, "_lock", Lock())

    def record(self, event_type: str, **payload: Any) -> None:
        if not self.enabled:
            return
        event = {
            "timestamp": _utc_now(),
            "event_type": event_type,
            **sanitize_mapping(payload),
        }
        line = json.dumps(event, ensure_ascii=False, sort_keys=False)
        lock: Lock = getattr(self, "_lock")
        with lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
