from __future__ import annotations

import re

from dba_assistant.application.request_models import (
    NormalizedRequest,
    RdbOverrides,
    RuntimeInputs,
    Secrets,
)


_SECRET_TOKEN_PATTERN = r"(?P<password>\"[^\"]+\"|'[^']+'|[^\s,;]+)"
_PASSWORD_PATTERNS = (
    re.compile(
        rf"(?i)\buse\s+{_SECRET_TOKEN_PATTERN}\s+as\s+(?:the\s+)?redis\s+password\b"
    ),
    re.compile(
        rf"(?i)\b(?:redis\s+)?password(?:\s+is|\s+to|\s+as)?\s+{_SECRET_TOKEN_PATTERN}"
    ),
    re.compile(
        rf"使用\s+{_SECRET_TOKEN_PATTERN}\s+作为\s*Redis\s*密码"
    ),
    re.compile(
        rf"(?:Redis\s*)?密码(?:是|为|：|:)?\s*{_SECRET_TOKEN_PATTERN}"
    ),
)
_HOST_PORT_PATTERN = re.compile(
    r"(?i)\b(?:redis\s+)?(?P<host>(?:localhost)|(?:\d{1,3}(?:\.\d{1,3}){3})|(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)*)):(?P<port>\d{1,5})\b"
)
_DB_PATTERN = re.compile(r"(?i)\bdb(?:\s+(?:index\s+)?)?(?P<db>\d+)\b")
_OUTPUT_MODE_PATTERN = re.compile(r"(?i)\b(?P<mode>report|summary)\b")
_PROFILE_PATTERN = re.compile(
    r"(?i)(?:(?<!\w)(?P<profile>generic|rcs)\s+profile(?!\w)|(?P<profile_cn>通用)\s+profile(?!\w))"
)
_PREFIX_PATTERN = re.compile(r"(?P<prefix>[\w.-]+:\*)")
_SECTION_TOP_PATTERN = re.compile(
    r"(?i)\b(?P<section>prefix|hash|list|set)\s+top\s+(?P<count>\d{1,4})\b"
)
_GENERIC_TOP_PATTERN = re.compile(
    r"(?i)(?<!prefix\s)(?<!hash\s)(?<!list\s)(?<!set\s)\btop\s+(?P<count>\d{1,4})\b"
)
_WHITESPACE_PATTERN = re.compile(r"\s+")


def normalize_raw_request(raw_prompt: str, *, default_output_mode: str) -> NormalizedRequest:
    password_match, password_pattern = _extract_password(raw_prompt)

    prompt = raw_prompt
    if password_match is not None and password_pattern is not None:
        prompt = password_pattern.sub(" ", prompt, count=1)
    prompt = _WHITESPACE_PATTERN.sub(" ", prompt).strip()

    host_match = _HOST_PORT_PATTERN.search(prompt)
    db_match = _DB_PATTERN.search(prompt)
    output_mode = _extract_output_mode(prompt, default_output_mode)

    return NormalizedRequest(
        raw_prompt=raw_prompt,
        prompt=prompt,
        runtime_inputs=RuntimeInputs(
            redis_host=host_match.group("host") if host_match else None,
            redis_port=int(host_match.group("port")) if host_match else 6379,
            redis_db=int(db_match.group("db")) if db_match else 0,
            output_mode=output_mode,
        ),
        secrets=Secrets(redis_password=_clean_secret(password_match.group("password")) if password_match else None),
        rdb_overrides=_extract_rdb_overrides(prompt),
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


def _extract_rdb_overrides(prompt: str) -> RdbOverrides:
    profile_name = _extract_profile_name(prompt)
    focus_prefixes = _extract_focus_prefixes(prompt)
    top_n = _extract_top_n_overrides(prompt)
    return RdbOverrides(profile_name=profile_name, focus_prefixes=focus_prefixes, top_n=top_n)


def _extract_profile_name(prompt: str) -> str | None:
    matches = list(_PROFILE_PATTERN.finditer(prompt))
    if not matches:
        return None

    match = matches[-1]
    profile = match.group("profile")
    if profile:
        return profile.lower()

    if match.group("profile_cn"):
        return "generic"

    return None


def _extract_focus_prefixes(prompt: str) -> tuple[str, ...]:
    prefixes: list[str] = []
    seen: set[str] = set()
    for match in _PREFIX_PATTERN.finditer(prompt):
        prefix = match.group("prefix")
        if prefix not in seen:
            seen.add(prefix)
            prefixes.append(prefix)
    return tuple(prefixes)


def _extract_top_n_overrides(prompt: str) -> dict[str, int]:
    top_n: dict[str, int] = {}
    for match in _SECTION_TOP_PATTERN.finditer(prompt):
        section = match.group("section").lower()
        count = int(match.group("count"))
        top_n[_map_section_to_top_key(section)] = count

    for match in _GENERIC_TOP_PATTERN.finditer(prompt):
        top_n["top_big_keys"] = int(match.group("count"))

    return top_n


def _map_section_to_top_key(section: str) -> str:
    return {
        "prefix": "prefix_top",
        "hash": "hash_big_keys",
        "list": "list_big_keys",
        "set": "set_big_keys",
    }[section]


def _clean_secret(value: str) -> str:
    return value.strip().strip("\"'")
