from __future__ import annotations

import re
from pathlib import Path

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
_WITH_PROFILE_PATTERN = re.compile(
    r"(?i)\bwith\s+(?:the\s+)?(?P<profile>generic|rcs)\s+profile(?![a-z0-9_])"
)
_USE_PROFILE_PATTERN = re.compile(
    r"(?i)\b(?:use|using|choose|select)\s+(?:the\s+)?(?P<profile>generic|rcs)\s+profile(?![a-z0-9_])"
)
_BY_PROFILE_PATTERN = re.compile(
    r"(?i)(?:按|用)\s*(?P<profile>generic|rcs)\s+profile(?![a-z0-9_])"
)
_CHINESE_GENERIC_PROFILE_PATTERN = re.compile(
    r"(?i)(?:按|用)\s*(?P<profile_cn>通用)\s*profile(?![a-z0-9_])"
)
_PREFIX_OVERRIDE_PATTERNS = (
    re.compile(
        r"(?i)(?:重点看|重点关注|关注|看|分析|analyze|analyse|inspect|focus(?:\s+on)?)\s*(?P<body>[^,;，。]*)"
    ),
)
_SECTION_TOP_PATTERN = re.compile(
    r"(?i)\b(?P<section>prefix|hash|list|set)\s+top\s+(?P<count>\d{1,4})\b"
)
_GENERIC_TOP_PATTERN = re.compile(
    r"(?i)(?<!prefix\s)(?<!hash\s)(?<!list\s)(?<!set\s)\btop\s+(?P<count>\d{1,4})(?=\s*(?:[,;，。]|$))"
)
_REPORT_OUTPUT_PATTERN = re.compile(
    r"(?i)(?:输出|导出|export|output|write|save)\s*(?:为|成|as|to|到|:|：)?\s*(?P<format>docx|pdf|html|summary)\b"
)
_REPORT_DESTINATION_PATTERN = re.compile(
    r"(?is)^\s*[\s,，、]*"
    r"(?:to|到|输出到|导出到|write\s+to|output\s+to|save\s+to|保存到|保存至)\s*(?P<path>.+?)"
    r"(?=\s*(?:and|but|then|also|plus|email|send|and\s+email|and\s+send|并且|并|然后|再|同时|此外|另外|但|但是|不过|然而|可是|而是|却)\b|[。!?，,;；]|$)"
)
_MYSQL_ROUTE_HINT_PATTERN = re.compile(
    r"(?i)mysql\s*(?:路径|路由|路线|route|path|pipeline)|(?:路径|路由|路线|route|path|pipeline)\s*mysql"
)
_NEGATION_PREFIX_PATTERN = re.compile(
    r"(?i)(?:不要|别|勿|禁止|禁用|\bdo\s+not\b|\bdon't\b|\bnever\b|\bnot\b)"
)
_CLAUSE_BREAK_PATTERN = re.compile(
    r"(?i)[,，。;；!?]|(?:\bbut\b|\bhowever\b|\bthough\b|\balthough\b|\binstead\b|\byet\b|\bexcept\b)|(?:但是|但|不过|然而|可是|而是|却|只是)"
)
_WHITESPACE_PATTERN = re.compile(r"\s+")
_MAX_TOP_N = 100


def normalize_raw_request(
    raw_prompt: str,
    *,
    default_output_mode: str,
    input_paths: list[Path] | tuple[Path, ...] | None = None,
) -> NormalizedRequest:
    password_match, password_pattern = _extract_password(raw_prompt)

    prompt = raw_prompt
    if password_match is not None and password_pattern is not None:
        prompt = password_pattern.sub(" ", prompt, count=1)
    prompt = _WHITESPACE_PATTERN.sub(" ", prompt).strip()

    host_match = _HOST_PORT_PATTERN.search(prompt)
    db_match = _DB_PATTERN.search(prompt)
    output_mode, report_format, output_path = _extract_report_output_intent(prompt, default_output_mode)
    route_name = _extract_route_name(prompt)

    return NormalizedRequest(
        raw_prompt=raw_prompt,
        prompt=prompt,
        runtime_inputs=RuntimeInputs(
            redis_host=host_match.group("host") if host_match else None,
            redis_port=int(host_match.group("port")) if host_match else 6379,
            redis_db=int(db_match.group("db")) if db_match else 0,
            output_mode=output_mode,
            report_format=report_format,
            output_path=output_path,
            input_paths=tuple(input_paths or ()),
        ),
        secrets=Secrets(redis_password=_clean_secret(password_match.group("password")) if password_match else None),
        rdb_overrides=_extract_rdb_overrides(prompt, route_name=route_name),
    )


def _extract_password(raw_prompt: str) -> tuple[re.Match[str] | None, re.Pattern[str] | None]:
    for pattern in _PASSWORD_PATTERNS:
        match = pattern.search(raw_prompt)
        if match:
            return match, pattern
    return None, None


def _extract_rdb_overrides(prompt: str, *, route_name: str | None = None) -> RdbOverrides:
    profile_name = _extract_profile_name(prompt)
    focus_prefixes = _extract_focus_prefixes(prompt)
    top_n = _extract_top_n_overrides(prompt)
    return RdbOverrides(
        profile_name=profile_name,
        route_name=route_name,
        focus_prefixes=focus_prefixes,
        top_n=top_n,
    )


def _extract_profile_name(prompt: str) -> str | None:
    matches: list[tuple[int, str]] = []

    for pattern in (_WITH_PROFILE_PATTERN, _USE_PROFILE_PATTERN, _BY_PROFILE_PATTERN):
        for match in pattern.finditer(prompt):
            if _has_negation_prefix(prompt, match.start()):
                continue
            matches.append((match.start(), match.group("profile").lower()))

    for match in _CHINESE_GENERIC_PROFILE_PATTERN.finditer(prompt):
        if _has_negation_prefix(prompt, match.start()):
            continue
        matches.append((match.start(), "generic"))

    if not matches:
        return None

    return max(matches, key=lambda item: item[0])[1]


def _extract_focus_prefixes(prompt: str) -> tuple[str, ...]:
    prefixes: list[str] = []
    seen: set[str] = set()
    for pattern in _PREFIX_OVERRIDE_PATTERNS:
        for match in pattern.finditer(prompt):
            body = match.group("body")
            for prefix_match in re.finditer(r"[A-Za-z0-9_.-]+:\*", body):
                prefix = prefix_match.group(0)
                if prefix not in seen:
                    seen.add(prefix)
                    prefixes.append(prefix)
    return tuple(prefixes)


def _extract_top_n_overrides(prompt: str) -> dict[str, int]:
    top_n: dict[str, int] = {}
    for match in _SECTION_TOP_PATTERN.finditer(prompt):
        section = match.group("section").lower()
        count = int(match.group("count"))
        if _is_valid_top_n(count):
            top_n[_map_section_to_top_key(section)] = count

    for match in _GENERIC_TOP_PATTERN.finditer(prompt):
        count = int(match.group("count"))
        if _is_valid_top_n(count):
            top_n["top_big_keys"] = count

    return top_n


def _extract_report_output_intent(
    prompt: str,
    default_output_mode: str,
) -> tuple[str, str | None, Path | None]:
    output_mode = default_output_mode
    report_format = None
    output_path = None

    for match in _REPORT_OUTPUT_PATTERN.finditer(prompt):
        if _has_negation_prefix(prompt, match.start()):
            continue

        output_token = match.group("format").lower()
        if output_token in {"docx", "pdf", "html"}:
            output_mode = "report"
            report_format = output_token
        elif output_token == "summary":
            output_mode = "summary"
            report_format = None

        path = _extract_report_output_path(prompt, match.end())
        if path is not None:
            output_path = path

    return output_mode, report_format, output_path


def _extract_route_name(prompt: str) -> str | None:
    for match in _MYSQL_ROUTE_HINT_PATTERN.finditer(prompt):
        if _has_negation_prefix(prompt, match.start()):
            continue
        return "legacy_sql_pipeline"
    return None


def _map_section_to_top_key(section: str) -> str:
    return {
        "prefix": "prefix_top",
        "hash": "hash_big_keys",
        "list": "list_big_keys",
        "set": "set_big_keys",
    }[section]


def _is_valid_top_n(count: int) -> bool:
    return 1 <= count <= _MAX_TOP_N


def _clean_secret(value: str) -> str:
    return value.strip().strip("\"'")


def _clean_output_path(value: str) -> str:
    return value.strip().rstrip("，。,.；;:：")


def _has_negation_prefix(prompt: str, match_start: int) -> bool:
    segment = _current_clause_segment(prompt, match_start)
    overlap = prompt[max(0, match_start - 1) : min(len(prompt), match_start + 1)]
    return (
        _NEGATION_PREFIX_PATTERN.search(segment) is not None
        or _NEGATION_PREFIX_PATTERN.search(overlap) is not None
    )


def _current_clause_segment(prompt: str, match_start: int) -> str:
    prefix = prompt[:match_start]
    last_break = None
    for break_match in _CLAUSE_BREAK_PATTERN.finditer(prefix):
        last_break = break_match.end()

    if last_break is None:
        return prefix
    return prefix[last_break:]


def _extract_report_output_path(prompt: str, start: int) -> Path | None:
    tail = prompt[start:]
    destination_match = _REPORT_DESTINATION_PATTERN.match(tail)
    if destination_match is None:
        return None

    raw_path = _clean_output_path(destination_match.group("path"))
    if not raw_path:
        return None

    if (raw_path.startswith('"') and raw_path.endswith('"')) or (
        raw_path.startswith("'") and raw_path.endswith("'")
    ):
        raw_path = raw_path[1:-1].strip()

    if not raw_path:
        return None

    return Path(raw_path).expanduser()
