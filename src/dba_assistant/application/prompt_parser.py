from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from dba_assistant.application.request_models import (
    NormalizedRequest,
    RdbOverrides,
    RuntimeInputs,
    Secrets,
)


_SECRET_TOKEN_PATTERN = r"(?P<password>\"[^\"]+\"|'[^']+'|[^\s,;，。；]+)"
_PASSWORD_PATTERNS = (
    re.compile(rf"(?i)\buse\s+{_SECRET_TOKEN_PATTERN}\s+as\s+(?:the\s+)?redis\s+password\b"),
    re.compile(rf"(?i)\b(?:redis\s+)?password(?:\s+is|\s+to|\s+as)?\s+{_SECRET_TOKEN_PATTERN}"),
    re.compile(rf"使用\s+{_SECRET_TOKEN_PATTERN}\s+作为\s*Redis\s*密码"),
    re.compile(rf"(?:Redis\s*)?密码(?:是|为|：|:)?\s*{_SECRET_TOKEN_PATTERN}"),
)
_MYSQL_PASSWORD_PATTERNS = (
    re.compile(rf"(?i)\bmysql\s+password(?:\s+is|\s+to|\s+as)?\s+{_SECRET_TOKEN_PATTERN}"),
    re.compile(rf"(?i)\bpassword(?:\s+is|\s+to|\s+as)?\s+{_SECRET_TOKEN_PATTERN}"),
    re.compile(rf"(?i)(?:mysql\s*)?密码(?:是|为|：|:)?\s*{_SECRET_TOKEN_PATTERN}"),
)
_REDIS_TOKEN_PATTERN = re.compile(r"(?i)(?<![a-z0-9_])redis(?![a-z0-9_])")
_MYSQL_TOKEN_PATTERN = re.compile(r"(?i)(?<![a-z0-9_])mysql(?![a-z0-9_])")
_SSH_TOKEN_PATTERN = re.compile(r"(?i)ssh")
_SSH_SECTION_END_PATTERN = re.compile(r"[。；;!?]")
_SSH_PASSWORD_PATTERN = re.compile(
    rf"(?i)(?:ssh\s*)?(?:密码(?:也是)?|password)\s*(?:是|为|：|:)?\s*(?P<password>\"[^\"]+\"|'[^']+'|[^\s,;，。；]+)"
)
_SSH_COMPACT_PATTERN = re.compile(
    r"(?i)\bssh\b\s+[^\s]+\s+[^\s/,:，。；;\"']+\s*/\s*(?P<password>[^\s,;，。；]+)"
)
_WHITESPACE_PATTERN = re.compile(r"\s+")
_CONTROL_TOKENS = {
    "docx",
    "summary",
    "report",
    "word",
}
_TOP_TOKEN_PATTERN = re.compile(r"(?i)^top\d+$")
_PREFIX_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+(?::[A-Za-z0-9_.-]+)*:\*$")


def normalize_raw_request(
    raw_prompt: str,
    *,
    default_output_mode: str,
    input_paths: list[Path] | tuple[Path, ...] | None = None,
) -> NormalizedRequest:
    ssh_secret = _extract_ssh_secret(raw_prompt)
    excluded_spans = _password_excluded_spans(ssh_secret)
    mysql_password_match, mysql_password_pattern = _extract_password(
        raw_prompt,
        scope="mysql",
        patterns=_MYSQL_PASSWORD_PATTERNS,
        excluded_spans=excluded_spans,
    )
    redis_password_match, redis_password_pattern = _extract_password(
        raw_prompt,
        scope="redis",
        patterns=_PASSWORD_PATTERNS,
        excluded_spans=excluded_spans,
    )

    prompt = raw_prompt
    prompt = _strip_span(prompt, ssh_secret.get("password_span") if ssh_secret else None)
    prompt = _strip_password_match(prompt, mysql_password_match, mysql_password_pattern)
    prompt = _strip_password_match(prompt, redis_password_match, redis_password_pattern)
    prompt = _WHITESPACE_PATTERN.sub(" ", prompt).strip()

    effective_input_paths = tuple(input_paths or ())
    input_kind = "local_rdb" if effective_input_paths else None

    return NormalizedRequest(
        raw_prompt=raw_prompt,
        prompt=prompt,
        runtime_inputs=RuntimeInputs(
            output_mode=default_output_mode,
            input_paths=effective_input_paths,
            input_kind=input_kind,
        ),
        secrets=Secrets(
            redis_password=_clean_secret(redis_password_match.group("password")) if redis_password_match else None,
            ssh_password=_clean_secret(ssh_secret["password"]) if ssh_secret and ssh_secret.get("password") else None,
            mysql_password=_clean_secret(mysql_password_match.group("password")) if mysql_password_match else None,
        ),
        rdb_overrides=RdbOverrides(),
    )


def normalize_requested_prefixes(tokens: object) -> tuple[str, ...]:
    if isinstance(tokens, str):
        raw_tokens: Iterable[str] = re.split(r"[\s,，、;；]+", tokens)
    elif isinstance(tokens, Iterable):
        raw_tokens = (str(token) for token in tokens)
    else:
        return ()

    normalized: list[str] = []
    seen: set[str] = set()
    for raw_token in raw_tokens:
        token = normalize_prefix_token(raw_token)
        if token is None or token in seen:
            continue
        seen.add(token)
        normalized.append(token)
    return tuple(normalized)


def normalize_prefix_token(token: str) -> str | None:
    cleaned = token.strip().strip("`'\"()[]{}")
    if not cleaned:
        return None
    lowered = cleaned.lower()
    if lowered in _CONTROL_TOKENS or _TOP_TOKEN_PATTERN.match(lowered):
        return None
    if not _PREFIX_TOKEN_PATTERN.match(cleaned):
        return None
    return cleaned


def _extract_password(
    raw_prompt: str,
    *,
    scope: str,
    patterns: tuple[re.Pattern[str], ...],
    excluded_spans: tuple[tuple[int, int], ...] = (),
) -> tuple[re.Match[str] | None, re.Pattern[str] | None]:
    for pattern in patterns:
        for match in pattern.finditer(raw_prompt):
            if _span_overlaps_excluded(match.span(), excluded_spans):
                continue
            if _classify_secret_scope(raw_prompt, match.start()) == scope:
                return match, pattern
    return None, None


def _extract_ssh_secret(raw_prompt: str) -> dict[str, object] | None:
    context_data = _extract_ssh_context(raw_prompt)
    if context_data is None:
        return None

    context, offset = context_data
    compact_match = _SSH_COMPACT_PATTERN.search(context)
    if compact_match is not None:
        return {
            "password": compact_match.group("password"),
            "password_span": (
                offset + compact_match.start("password"),
                offset + compact_match.end("password"),
            ),
        }

    password_match = _SSH_PASSWORD_PATTERN.search(context)
    if password_match is None:
        return None

    return {
        "password": password_match.group("password"),
        "password_span": (
            offset + password_match.start("password"),
            offset + password_match.end("password"),
        ),
    }


def _extract_ssh_context(raw_prompt: str) -> tuple[str, int] | None:
    match = _SSH_TOKEN_PATTERN.search(raw_prompt)
    if match is None:
        return None

    start = match.start()
    end_match = _SSH_SECTION_END_PATTERN.search(raw_prompt, pos=match.end())
    end = end_match.start() if end_match is not None else len(raw_prompt)
    return raw_prompt[start:end], start


def _password_excluded_spans(ssh_secret: dict[str, object] | None) -> tuple[tuple[int, int], ...]:
    if ssh_secret is None:
        return ()
    span = ssh_secret.get("password_span")
    if not isinstance(span, tuple) or len(span) != 2:
        return ()
    return (span,)


def _strip_password_match(
    prompt: str,
    match: re.Match[str] | None,
    pattern: re.Pattern[str] | None,
) -> str:
    if match is None or pattern is None:
        return prompt
    return pattern.sub(" ", prompt, count=1)


def _strip_span(prompt: str, span: tuple[int, int] | None) -> str:
    if span is None:
        return prompt
    start, end = span
    return f"{prompt[:start]} {prompt[end:]}"


def _span_overlaps_excluded(span: tuple[int, int], excluded_spans: tuple[tuple[int, int], ...]) -> bool:
    start, end = span
    for excluded_start, excluded_end in excluded_spans:
        if start < excluded_end and end > excluded_start:
            return True
    return False


def _classify_secret_scope(prompt: str, match_start: int) -> str | None:
    redis_distance = _nearest_scope_distance(prompt, _REDIS_TOKEN_PATTERN, match_start)
    mysql_distance = _nearest_scope_distance(prompt, _MYSQL_TOKEN_PATTERN, match_start)
    if redis_distance is None and mysql_distance is None:
        return None
    if redis_distance is None:
        return "mysql"
    if mysql_distance is None:
        return "redis"
    return "redis" if redis_distance <= mysql_distance else "mysql"


def _nearest_scope_distance(prompt: str, pattern: re.Pattern[str], match_start: int) -> int | None:
    distances = [abs(scope_match.start() - match_start) for scope_match in pattern.finditer(prompt)]
    return min(distances) if distances else None


def _clean_secret(value: str) -> str:
    return value.strip().strip("\"'")
