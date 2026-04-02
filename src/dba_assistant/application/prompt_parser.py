from __future__ import annotations

import re

from dba_assistant.application.request_models import NormalizedRequest, RuntimeInputs, Secrets


_PASSWORD_PATTERNS = (
    re.compile(
        r"(?i)\b(?:redis\s+)?password(?:\s+is|\s+to|\s+as)?\s+(?P<password>[^\s,;:.]+)"
    ),
    re.compile(r"(?i)\buse\s+(?P<password>[^\s,;:.]+)\s+as\s+(?:the\s+)?redis\s+password\b"),
)
_HOST_PORT_PATTERN = re.compile(
    r"(?i)\b(?:redis\s+)?(?P<host>(?:localhost)|(?:\d{1,3}(?:\.\d{1,3}){3})|(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)*)):(?P<port>\d{1,5})\b"
)
_DB_PATTERN = re.compile(r"(?i)\bdb(?:\s+(?:index\s+)?)?(?P<db>\d+)\b")
_OUTPUT_MODE_PATTERN = re.compile(r"(?i)\b(?P<mode>report|summary)\b")
_WHITESPACE_PATTERN = re.compile(r"\s+")


def normalize_raw_request(raw_prompt: str, *, default_output_mode: str) -> NormalizedRequest:
    password_match, password_pattern = _extract_password(raw_prompt)
    host_match = _HOST_PORT_PATTERN.search(raw_prompt)
    db_match = _DB_PATTERN.search(raw_prompt)
    output_mode = _extract_output_mode(raw_prompt, default_output_mode)

    prompt = raw_prompt
    if password_match is not None and password_pattern is not None:
        prompt = password_pattern.sub(" ", prompt, count=1)
    prompt = _WHITESPACE_PATTERN.sub(" ", prompt).strip()

    return NormalizedRequest(
        raw_prompt=raw_prompt,
        prompt=prompt,
        runtime_inputs=RuntimeInputs(
            redis_host=host_match.group("host") if host_match else None,
            redis_port=int(host_match.group("port")) if host_match else 6379,
            redis_db=int(db_match.group("db")) if db_match else 0,
            output_mode=output_mode,
        ),
        secrets=Secrets(redis_password=password_match.group("password") if password_match else None),
    )


def _extract_password(raw_prompt: str) -> tuple[re.Match[str] | None, re.Pattern[str] | None]:
    for pattern in _PASSWORD_PATTERNS:
        match = pattern.search(raw_prompt)
        if match:
            return match, pattern
    return None, None


def _extract_output_mode(raw_prompt: str, default_output_mode: str) -> str:
    matches = list(_OUTPUT_MODE_PATTERN.finditer(raw_prompt))
    if not matches:
        return default_output_mode

    return matches[-1].group("mode").lower()
