from __future__ import annotations

import re
from pathlib import Path

from dba_assistant.application.request_models import (
    NormalizedRequest,
    RdbOverrides,
    RuntimeInputs,
    Secrets,
)
from dba_assistant.core.reporter.output_path_policy import infer_report_format_alias


_HOST_PATTERN = (
    r"(?:localhost)|(?:\d{1,3}(?:\.\d{1,3}){3})|"
    r"(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?"
    r"(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)*)"
)
_SECRET_TOKEN_PATTERN = r"(?P<password>\"[^\"]+\"|'[^']+'|[^\s,;，。；]+)"
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
    rf"(?i)\b(?P<host>{_HOST_PATTERN}):(?P<port>\d{{1,5}})\b"
)
_MYSQL_HOST_PORT_PATTERN = re.compile(
    rf"(?i)(?<![a-z0-9_])mysql(?![a-z0-9_])(?:\s*(?:信息如下|信息|如下|host|server|地址|from|at|on|从))?\s*"
    rf"(?:是|为|：|:)?\s*(?P<host>{_HOST_PATTERN}):(?P<port>\d{{1,5}})\b"
)
_DB_PATTERN = re.compile(r"(?i)\bdb(?:\s+(?:index\s+)?)?(?P<db>\d+)\b")
_RDB_PATH_PATTERN = re.compile(
    r"(?P<path>(?:~|\.{1,2}|/)[^\s,;，。\"']*\.rdb\b)"
)
_MYSQL_USER_PATTERN = re.compile(
    r"(?i)(?:用户名|username|user)\s*(?:是|为|：|:)?\s*(?P<user>[^\s,;，。\"']+)"
)
_MYSQL_DATABASE_PATTERN = re.compile(
    r"(?i)(?:数据库|database)\s*(?:是|为|：|:)?\s*(?P<database>[^\s,;，。\"']+)"
)
_MYSQL_DATABASE_ALIAS_PATTERN = re.compile(
    r"(?i)(?:的\s*)?(?P<database>[A-Za-z_][A-Za-z0-9_$]*)\s*库(?:里|中)?"
)
_MYSQL_TABLE_PATTERN = re.compile(
    r"(?i)(?:表名|表|table)\s*(?:叫|是|为|：|:)?\s*(?P<table>[A-Za-z_][A-Za-z0-9_$.]*)"
)
_MYSQL_QUERY_PATTERN = re.compile(
    r"(?is)(?:查询|query)\s*(?P<quote>\"|')(?P<query>.+?)(?P=quote)"
)
_MYSQL_UNQUOTED_QUERY_PATTERN = re.compile(
    r"(?is)(?:执行|execute|run|query)\s+(?P<query>(?:select|with)\b.+?)(?=\s*(?:[,，。;；]|$))"
)
_MYSQL_TOKEN_PATTERN = re.compile(r"(?i)(?<![a-z0-9_])mysql(?![a-z0-9_])")
_REDIS_TOKEN_PATTERN = re.compile(r"(?i)(?<![a-z0-9_])redis(?![a-z0-9_])")
_SSH_TOKEN_PATTERN = re.compile(r"(?i)ssh")
_SSH_SECTION_END_PATTERN = re.compile(r"[。；;!?]")
_SSH_COMPACT_PATTERN = re.compile(
    rf"(?i)\bssh\b\s+(?P<host>{_HOST_PATTERN})(?::(?P<port>\d{{1,5}}))?"
    rf"\s+(?P<username>[^\s/,:，。；;\"']+)\s*/\s*(?P<password>[^\s,;，。；]+)"
)
_SSH_HOST_INLINE_PATTERN = re.compile(
    rf"(?i)\bssh\b(?:\s+(?:host|server|主机|主机地址))?\s*(?P<host>{_HOST_PATTERN})"
    rf"(?::(?P<port>\d{{1,5}}))?"
)
_SSH_HOST_FIELD_PATTERN = re.compile(
    rf"(?i)(?:主机地址|ssh\s+host|ssh\s+server|host|server|主机)\s*"
    rf"(?:是|为|：|:)?\s*(?P<host>{_HOST_PATTERN})(?::(?P<port>\d{{1,5}}))?"
)
_SSH_PORT_PATTERN = re.compile(
    r"(?i)(?:ssh\s*)?(?:port|端口)\s*(?:是|为|：|:)?\s*(?P<port>\d{1,5})"
)
_SSH_USERNAME_PATTERN = re.compile(
    r"(?i)(?:ssh\s*)?(?:用户名|username|user)\s*(?:是|为|：|:)?\s*(?P<username>[^\s,;，。/\"']+)"
)
_SSH_PASSWORD_PATTERN = re.compile(
    rf"(?i)(?:ssh\s*)?(?:密码(?:也是)?|password)\s*(?:是|为|：|:)?\s*(?P<password>\"[^\"]+\"|'[^']+'|[^\s,;，。；]+)"
)
_LATEST_RDB_PATTERN = re.compile(
    r"(?i)(?:最新(?:的)?\s*(?:rdb|快照)|latest\s+(?:rdb|snapshot)|fresh\s+snapshot|生成最新快照)"
)
_REMOTE_RDB_PATH_HINT_PATTERN = re.compile(
    r"(?i)(?:rdb(?:文件|file)?\s*(?:在|位于|路径(?:是|为)?|path(?:\s+is|\s+at)?))"
)


def _build_profile_alternation() -> str:
    """Build a regex alternation from available profile YAML files."""
    try:
        from dba_assistant.capabilities.redis_rdb_analysis.profile_resolver import (
            available_profile_names,
        )
        names = available_profile_names()
    except Exception:  # noqa: BLE001
        names = []
    if not names:
        names = ["generic", "rcs"]
    return "|".join(re.escape(n) for n in names)


_PROFILE_ALT = _build_profile_alternation()
_PROFILE_HINT_PATTERNS = (
    re.compile(
        rf"(?i)\bwith\s+(?:the\s+)?(?P<profile>{_PROFILE_ALT}|generic)\s+profile(?![a-z0-9_])"
    ),
    re.compile(
        rf"(?i)\b(?:use|using|choose|select)\s+(?:the\s+)?(?P<profile>{_PROFILE_ALT}|generic)\s+"
        rf"(?:profile|template|report(?:\s+style)?|config)(?![a-z0-9_])"
    ),
    re.compile(
        rf"(?i)(?:使用|指定|按|用|采用|选择|按照)\s*(?P<profile>{_PROFILE_ALT}|通用)\s*"
        rf"(?:profile|模板|报告(?:风格)?|配置)(?![a-z0-9_])"
    ),
)
_RAW_PREFIX_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_.-]+(?::[A-Za-z0-9_.-]+)*(?::\*)?")
_PREFIX_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_.-]+(?::[A-Za-z0-9_.-]+)*:\*")
_PREFIX_CANDIDATE_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+(?::[A-Za-z0-9_.-]+)*(?::\*)?$")
_PREFIX_KEYWORD_PATTERN = re.compile(r"(?i)\bkeys?\b|键|前缀|详情")
_PREFIX_INTENT_OPENERS = (
    "只需要输出",
    "只需要",
    "只需",
    "只输出",
    "只看",
    "重点分析",
    "重点看",
    "重点关注",
    "关注",
    "只分析",
    "查看前缀",
    "指定前缀",
    "前缀为",
    "前缀是",
    "前缀",
    "focus on",
    "focus",
)
_PREFIX_CONTINUATION_PATTERN = re.compile(
    r"(?i)^(?:一个是|另一个是|另一个前缀是|前缀为|前缀是|分别是|还有|以及|和|与|及|and\b)"
)
_PREFIX_CONTEXT_MARKER_PATTERN = re.compile(r"(?i)\bkeys?\b|\bprefix\b|键|前缀|详情")
_PREFIX_TOKEN_STOPWORDS = {
    "a",
    "all",
    "analysis",
    "and",
    "detail",
    "details",
    "focus",
    "generic",
    "key",
    "keys",
    "need",
    "only",
    "output",
    "prefix",
    "profile",
    "rcs",
    "report",
    "the",
    "top",
}
_FOCUS_ONLY_PATTERNS = (
    re.compile(r"其他(?:分析结果|结果|内容|章节|报告中其他(?:的)?内容)?都不需要"),
    re.compile(r"报告中其他(?:的)?都不需要"),
    re.compile(r"(?i)(?:only\s+need|only\s+output).*(?:keys?|prefix)"),
    re.compile(r"(?:只需要输出|只需要|只输出).*(?:key|keys|键|前缀)"),
    re.compile(r"(?:只输出(?:这些|对应|指定)?前缀详情|只输出对应前缀详情)"),
)
_PREFIX_INTENT_PATTERN = re.compile(
    r"(?i)^(?:我)?\s*(?:只需要输出|只需要|只需|只输出|只看|重点分析|重点看|重点关注|关注|只分析|查看前缀|指定前缀|前缀为|前缀是|前缀|focus\s+on|focus)"
)
_SECTION_ALIAS_TO_TOP_KEY = {
    "prefix": "prefix_top",
    "前缀": "prefix_top",
    "string": "string_big_keys",
    "hash": "hash_big_keys",
    "list": "list_big_keys",
    "set": "set_big_keys",
    "zset": "zset_big_keys",
    "stream": "stream_big_keys",
    "other": "other_big_keys",
}
_SECTION_TOP_PATTERN = re.compile(
    r"(?i)(?P<section>prefix|前缀|string|hash|list|set|zset|stream|other)\s*top\s*(?P<count>\d{1,4})\b"
)
_GENERIC_TOP_PATTERNS = (
    re.compile(r"(?i)\btop\s*(?P<count>\d{1,4})\b"),
    re.compile(r"前\s*(?P<count>\d{1,4})(?=\s*(?:个|条|项|[,;，。]|$))"),
)
_SUMMARY_TOP_N_SKIP_PATTERN = re.compile(r"(?i)\bsummary\b|结论|findings?")
_REPORT_OUTPUT_PATTERN = re.compile(
    r"(?i)(?:输出|导出|export|output|write|save)\s*(?:为|成|as|to|到|:|：)?\s*"
    r"(?P<format>"
    r"docx(?:\s*/\s*word(?:\s*(?:file|document)|文件|文档)?)?"
    r"|word(?:\s*(?:file|document)|文件|文档)?"
    r"|pdf|html|summary"
    r")"
)
_REPORT_DESTINATION_PATTERN = re.compile(
    r"(?is)^\s*[\s,，、]*"
    r"(?:to|到|输出到|导出到|write\s+to|output\s+to|save\s+to|保存到|保存至)\s*(?P<path>.+?)\s*$"
)
_MYSQL_ROUTE_HINT_PATTERN = re.compile(
    r"(?i)mysql\s*(?:路径|路由|路线|route|path|pipeline)|(?:路径|路由|路线|route|path|pipeline)\s*mysql"
)
_NEGATION_PREFIX_PATTERN = re.compile(
    r"(?i)(?:不要|别|勿|禁止|禁用|\bdo\s+not\b|\bdon't\b|\bnever\b|\bnot\b(?!\s+only\b))"
)
_CLAUSE_BREAK_PATTERN = re.compile(
    r"(?i)[,，。;；!?]|(?:\bbut\b|\bhowever\b|\bthough\b|\balthough\b|\binstead\b|\byet\b|\bexcept\b)|(?:但是|但|不过|然而|可是|而是|却|只是)"
)
_WHITESPACE_PATTERN = re.compile(r"\s+")
_ENGLISH_REPORT_PATTERN = re.compile(r"(?i)(?:\benglish\b|in\s+english|英文版|输出英文|英文报告)")
_CHINESE_REPORT_PATTERN = re.compile(r"(?i)(?:\bchinese\b|中文|中文版|输出中文|中文报告)")
_MAX_TOP_N = 1000


def normalize_raw_request(
    raw_prompt: str,
    *,
    default_output_mode: str,
    input_paths: list[Path] | tuple[Path, ...] | None = None,
) -> NormalizedRequest:
    ssh_details = _extract_ssh_connection(raw_prompt)
    excluded_spans = _password_excluded_spans(ssh_details)
    redis_password_match, redis_password_pattern = _extract_password(
        raw_prompt,
        scope="redis",
        excluded_spans=excluded_spans,
    )
    mysql_password_match, mysql_password_pattern = _extract_password(
        raw_prompt,
        scope="mysql",
        excluded_spans=excluded_spans,
    )

    prompt = raw_prompt
    prompt = _strip_span(prompt, ssh_details.get("password_span") if ssh_details else None)
    prompt = _strip_password_match(prompt, mysql_password_match, mysql_password_pattern)
    prompt = _strip_password_match(prompt, redis_password_match, redis_password_pattern)
    prompt = _WHITESPACE_PATTERN.sub(" ", prompt).strip()

    mysql_host, mysql_port, mysql_context_span = _extract_mysql_target(prompt)
    host_match = _extract_redis_target(prompt, excluded_span=mysql_context_span)
    db_match = _DB_PATTERN.search(prompt)
    output_mode, report_format, output_path = _extract_report_output_intent(prompt, default_output_mode)
    report_language = _extract_report_language(prompt)
    route_name = _extract_route_name(prompt)
    remote_rdb_path = _extract_remote_rdb_path(
        prompt,
        has_remote_context=bool(host_match or ssh_details),
    )
    prompt_input_paths = _extract_prompt_input_paths(prompt, exclude_path=remote_rdb_path)
    effective_input_paths = tuple(input_paths or prompt_input_paths)
    mysql_query, mysql_query_span = _extract_mysql_query(prompt)
    mysql_context = _mysql_connection_context(prompt, mysql_query_span)
    mysql_user = _extract_mysql_field(mysql_context, _MYSQL_USER_PATTERN, "user")
    mysql_database = _extract_mysql_database(mysql_context)
    mysql_table = _extract_mysql_field(mysql_context, _MYSQL_TABLE_PATTERN, "table")
    input_kind = _infer_input_kind(
        input_paths=effective_input_paths,
        redis_host=host_match.group("host") if host_match else None,
        mysql_table=mysql_table,
        mysql_query=mysql_query,
    )

    return NormalizedRequest(
        raw_prompt=raw_prompt,
        prompt=prompt,
        runtime_inputs=RuntimeInputs(
            redis_host=host_match.group("host") if host_match else None,
            redis_port=int(host_match.group("port")) if host_match else 6379,
            redis_db=int(db_match.group("db")) if db_match else 0,
            output_mode=output_mode,
            report_language=report_language,
            report_format=report_format,
            output_path=output_path,
            input_paths=effective_input_paths,
            input_kind=input_kind,
            ssh_host=ssh_details.get("host") if ssh_details else None,
            ssh_port=ssh_details.get("port") if ssh_details else None,
            ssh_username=ssh_details.get("username") if ssh_details else None,
            remote_rdb_path=remote_rdb_path,
            remote_rdb_path_source="user_override" if remote_rdb_path else None,
            mysql_host=mysql_host,
            mysql_port=mysql_port or 3306,
            mysql_user=mysql_user,
            mysql_database=mysql_database,
            mysql_table=mysql_table,
            mysql_query=mysql_query,
            require_fresh_rdb_snapshot=_extract_latest_rdb_request(prompt),
        ),
        secrets=Secrets(
            redis_password=_clean_secret(redis_password_match.group("password")) if redis_password_match else None,
            ssh_password=_clean_secret(ssh_details["password"]) if ssh_details and ssh_details.get("password") else None,
            mysql_password=_clean_secret(mysql_password_match.group("password")) if mysql_password_match else None,
        ),
        rdb_overrides=_extract_rdb_overrides(prompt, route_name=route_name),
    )


def _extract_password(
    raw_prompt: str,
    *,
    scope: str,
    excluded_spans: tuple[tuple[int, int], ...] = (),
) -> tuple[re.Match[str] | None, re.Pattern[str] | None]:
    for pattern in _PASSWORD_PATTERNS:
        for match in pattern.finditer(raw_prompt):
            if _span_overlaps_excluded(match.span(), excluded_spans):
                continue
            if _classify_secret_scope(raw_prompt, match.start()) == scope:
                return match, pattern
    return None, None


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


def _extract_rdb_overrides(prompt: str, *, route_name: str | None = None) -> RdbOverrides:
    profile_name = _extract_profile_name(prompt)
    focus_prefixes = _extract_focus_prefixes(prompt)
    focus_only = _extract_focus_only(prompt, focus_prefixes=focus_prefixes)
    top_n = _extract_top_n_overrides(prompt)
    return RdbOverrides(
        profile_name=profile_name,
        route_name=route_name,
        focus_prefixes=focus_prefixes,
        focus_only=focus_only,
        top_n=top_n,
    )


def _extract_ssh_connection(raw_prompt: str) -> dict[str, object] | None:
    context_data = _extract_ssh_context(raw_prompt)
    if context_data is None:
        return None

    context, offset = context_data
    host = None
    port = None
    username = None
    password = None
    password_span = None

    compact_match = _SSH_COMPACT_PATTERN.search(context)
    if compact_match is not None:
        host = compact_match.group("host")
        port_value = compact_match.group("port")
        port = int(port_value) if port_value else 22
        username = compact_match.group("username")
        password = compact_match.group("password")
        password_span = (
            offset + compact_match.start("password"),
            offset + compact_match.end("password"),
        )
    else:
        host_match = _SSH_HOST_INLINE_PATTERN.search(context) or _SSH_HOST_FIELD_PATTERN.search(context)
        if host_match is not None:
            host = host_match.group("host")
            port_value = host_match.group("port")
            if port_value:
                port = int(port_value)

        port_match = _SSH_PORT_PATTERN.search(context)
        if port_match is not None:
            port = int(port_match.group("port"))

        username_match = _SSH_USERNAME_PATTERN.search(context)
        if username_match is not None:
            username = username_match.group("username")

        password_match = _SSH_PASSWORD_PATTERN.search(context)
        if password_match is not None:
            password = password_match.group("password")
            password_span = (
                offset + password_match.start("password"),
                offset + password_match.end("password"),
            )

    if host is None and username is None and password is None:
        return None

    return {
        "host": host,
        "port": port or 22,
        "username": username,
        "password": password,
        "password_span": password_span,
        "context_span": (offset, offset + len(context)),
    }


def _extract_ssh_context(raw_prompt: str) -> tuple[str, int] | None:
    match = _SSH_TOKEN_PATTERN.search(raw_prompt)
    if match is None:
        return None

    start = match.start()
    tail = raw_prompt[start:]
    end_match = _SSH_SECTION_END_PATTERN.search(tail)
    if end_match is None:
        return tail, start
    return tail[: end_match.start()], start


def _password_excluded_spans(ssh_details: dict[str, object] | None) -> tuple[tuple[int, int], ...]:
    if ssh_details is None:
        return ()
    context_span = ssh_details.get("context_span")
    if not isinstance(context_span, tuple):
        return ()
    return (context_span,)


def _span_overlaps_excluded(
    span: tuple[int, int],
    excluded_spans: tuple[tuple[int, int], ...],
) -> bool:
    start, end = span
    for excluded_start, excluded_end in excluded_spans:
        if start < excluded_end and end > excluded_start:
            return True
    return False


def _extract_latest_rdb_request(prompt: str) -> bool:
    return _LATEST_RDB_PATTERN.search(prompt) is not None


def _extract_remote_rdb_path(
    prompt: str,
    *,
    has_remote_context: bool,
) -> str | None:
    if not has_remote_context:
        return None

    matches = list(_RDB_PATH_PATTERN.finditer(prompt))
    if not matches:
        return None

    for match in matches:
        if _REMOTE_RDB_PATH_HINT_PATTERN.search(prompt[max(0, match.start() - 32):match.start()]):
            return str(Path(match.group("path")))

    if len(matches) == 1:
        return str(Path(matches[0].group("path")))
    return None


def _extract_profile_name(prompt: str) -> str | None:
    matches: list[tuple[int, str, bool]] = []

    for pattern in _PROFILE_HINT_PATTERNS:
        for match in pattern.finditer(prompt):
            profile = _normalize_profile_alias(match.group("profile"))
            matches.append((match.start(), profile, _has_negation_prefix(prompt, match.start())))

    if not matches:
        return None

    value = None
    for _, profile, negated in sorted(matches, key=lambda item: item[0]):
        if negated:
            if value == profile:
                value = None
            continue
        value = profile
    return value


def _extract_focus_prefixes(prompt: str) -> tuple[str, ...]:
    clauses = _iter_prompt_clauses(prompt)
    prefixes: list[str] = []
    seen: set[str] = set()
    carry_prefix_context = False

    for clause in clauses:
        clause_prefixes: tuple[str, ...] = ()
        if _looks_like_prefix_clause(clause):
            carry_prefix_context = True
            clause_prefixes = _extract_prefix_candidates_from_clause(clause)
        elif carry_prefix_context and _continues_prefix_clause(clause):
            clause_prefixes = _extract_prefix_candidates_from_clause(clause)
        else:
            carry_prefix_context = False
            continue

        for prefix in clause_prefixes:
            if prefix not in seen:
                seen.add(prefix)
                prefixes.append(prefix)

        if not (_mentions_prefix_context(clause) or clause_prefixes):
            carry_prefix_context = False

    return tuple(prefixes)


def _extract_top_n_overrides(prompt: str) -> dict[str, int]:
    top_n: dict[str, int] = {}
    for clause in _iter_prompt_clauses(prompt):
        generic_count = _extract_generic_top_n_from_clause(clause)
        if generic_count is not None:
            for key, value in _expand_generic_top_n(generic_count).items():
                top_n.setdefault(key, value)

        for match in _SECTION_TOP_PATTERN.finditer(clause):
            section = match.group("section").lower()
            count = int(match.group("count"))
            if _is_valid_top_n(count):
                top_n[_map_section_to_top_key(section)] = count

    return top_n


def _extract_focus_only(prompt: str, *, focus_prefixes: tuple[str, ...]) -> bool:
    if not focus_prefixes:
        return False
    for clause in _iter_prompt_clauses(prompt):
        if any(pattern.search(clause) for pattern in _FOCUS_ONLY_PATTERNS):
            return True
    return False


def _extract_report_output_intent(
    prompt: str,
    default_output_mode: str,
) -> tuple[str, str | None, Path | None]:
    output_mode = default_output_mode
    report_format = None
    output_path = None

    matches = sorted(_REPORT_OUTPUT_PATTERN.finditer(prompt), key=lambda match: match.start())

    for match in matches:
        output_token = infer_report_format_alias(match.group("format")) or match.group("format").lower()
        if _has_negation_prefix(prompt, match.start()):
            if output_token == report_format or (output_token == "summary" and output_mode == "summary"):
                output_mode = default_output_mode
                report_format = None
                output_path = None
            continue

        if output_token in {"docx", "pdf", "html"}:
            output_mode = "report"
            report_format = output_token
        elif output_token == "summary":
            output_mode = "summary"
            report_format = None

        path = _extract_report_output_path(prompt, match.end())
        output_path = path

    return output_mode, report_format, output_path


def _extract_route_name(prompt: str) -> str | None:
    route_name = None
    for match in sorted(_MYSQL_ROUTE_HINT_PATTERN.finditer(prompt), key=lambda match: match.start()):
        route_name = None if _has_negation_prefix(prompt, match.start()) else "database_backed_analysis"
    return route_name


def _extract_prompt_input_paths(prompt: str, *, exclude_path: str | None = None) -> tuple[Path, ...]:
    seen: set[Path] = set()
    paths: list[Path] = []
    for match in _RDB_PATH_PATTERN.finditer(prompt):
        path = Path(match.group("path")).expanduser()
        if exclude_path is not None and str(path) == exclude_path:
            continue
        if path not in seen:
            seen.add(path)
            paths.append(path)
    return tuple(paths)


def _extract_mysql_target(prompt: str) -> tuple[str | None, int | None, tuple[int, int] | None]:
    match = _MYSQL_HOST_PORT_PATTERN.search(prompt)
    if match is None:
        return None, None, None
    return match.group("host"), int(match.group("port")), match.span()


def _extract_redis_target(
    prompt: str,
    *,
    excluded_span: tuple[int, int] | None,
) -> re.Match[str] | None:
    for match in _HOST_PORT_PATTERN.finditer(prompt):
        if excluded_span is not None:
            start, end = match.span()
            if start >= excluded_span[0] and end <= excluded_span[1]:
                continue
        return match
    return None


def _extract_mysql_field(
    prompt: str,
    pattern: re.Pattern[str],
    group_name: str,
) -> str | None:
    if not _MYSQL_TOKEN_PATTERN.search(prompt):
        return None
    match = pattern.search(prompt)
    if match is None:
        return None
    return match.group(group_name)


def _extract_mysql_query(prompt: str) -> str | None:
    if not _MYSQL_TOKEN_PATTERN.search(prompt):
        return None, None
    match = _MYSQL_QUERY_PATTERN.search(prompt)
    if match is not None:
        return match.group("query").strip(), match.span("query")
    match = _MYSQL_UNQUOTED_QUERY_PATTERN.search(prompt)
    if match is None:
        return None, None
    return match.group("query").strip(), match.span("query")


def _extract_mysql_database(prompt: str) -> str | None:
    if not _MYSQL_TOKEN_PATTERN.search(prompt):
        return None
    match = _MYSQL_DATABASE_PATTERN.search(prompt)
    if match is not None:
        return match.group("database")
    match = _MYSQL_DATABASE_ALIAS_PATTERN.search(prompt)
    if match is None:
        return None
    return match.group("database")


def _mysql_connection_context(
    prompt: str,
    mysql_query_span: tuple[int, int] | None,
) -> str:
    if mysql_query_span is None:
        return prompt
    return prompt[: mysql_query_span[0]]


def _infer_input_kind(
    *,
    input_paths: tuple[Path, ...],
    redis_host: str | None,
    mysql_table: str | None,
    mysql_query: str | None,
) -> str | None:
    if input_paths:
        return "local_rdb"
    if redis_host:
        return "remote_redis"
    if mysql_table or mysql_query:
        return "preparsed_mysql"
    return None


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


def _map_section_to_top_key(section: str) -> str:
    return _SECTION_ALIAS_TO_TOP_KEY[section]


def _is_valid_top_n(count: int) -> bool:
    return 1 <= count <= _MAX_TOP_N


def _extract_report_language(prompt: str) -> str:
    last_match_start = -1
    language = "zh-CN"
    for pattern, code in ((_CHINESE_REPORT_PATTERN, "zh-CN"), (_ENGLISH_REPORT_PATTERN, "en-US")):
        for match in pattern.finditer(prompt):
            if _has_negation_prefix(prompt, match.start()):
                continue
            if match.start() >= last_match_start:
                last_match_start = match.start()
                language = code
    return language


def _normalize_profile_alias(value: str) -> str:
    normalized = value.strip().lower()
    if normalized == "通用":
        return "generic"
    return normalized


def _iter_prompt_clauses(prompt: str) -> tuple[str, ...]:
    clauses = [segment.strip() for segment in _CLAUSE_BREAK_PATTERN.split(prompt) if segment.strip()]
    return tuple(clauses)


def _extract_prefix_candidates_from_clause(clause: str) -> tuple[str, ...]:
    body = clause.strip()
    body = _strip_prefix_clause_intro(body)
    body = re.sub(r"^(?:一个是|另一个是|另一个前缀是|分别是|还有|以及|和|与|及)\s*", "", body)
    body = re.sub(r"^(?:前缀(?:为|是)?\s*)", "", body)
    body = re.sub(r"(?i)\b(?:these|those|corresponding|specified)\b", " ", body)
    body = re.sub(r"(?:这些|对应|指定|用户指定的|对应前缀|默认前缀|两个前缀|多个前缀|两个|多个|一个|另一个)", " ", body)
    body = re.sub(r"(?i)\bkeys?\b", " ", body)
    body = re.sub(r"(?i)\b(?:analysis|top)\b", " ", body)
    body = re.sub(r"(?:键|前缀|详情|分析|重点)", " ", body)
    body = body.replace("的", " ")

    raw_tokens = [match.group(0) for match in _RAW_PREFIX_TOKEN_PATTERN.finditer(body)]
    return normalize_requested_prefixes(raw_tokens)


def _looks_like_prefix_clause(clause: str) -> bool:
    if _PREFIX_INTENT_PATTERN.search(clause):
        return True
    lower_clause = clause.lower()
    if any(opener in lower_clause for opener in _PREFIX_INTENT_OPENERS if opener.isascii()):
        return True
    if any(opener in clause for opener in _PREFIX_INTENT_OPENERS if not opener.isascii()):
        return True
    if _PREFIX_TOKEN_PATTERN.search(clause) and _PREFIX_KEYWORD_PATTERN.search(clause):
        return True
    if ("前缀为" in clause or "前缀是" in clause) and _PREFIX_KEYWORD_PATTERN.search(clause):
        return True
    return False


def _continues_prefix_clause(clause: str) -> bool:
    if _PREFIX_CONTINUATION_PATTERN.search(clause):
        return True
    if _mentions_prefix_context(clause):
        return True
    if _SECTION_TOP_PATTERN.search(clause) or _extract_generic_top_n_from_clause(clause) is not None:
        return False
    return bool(normalize_requested_prefixes(match.group(0) for match in _RAW_PREFIX_TOKEN_PATTERN.finditer(clause)))


def _mentions_prefix_context(clause: str) -> bool:
    if _PREFIX_KEYWORD_PATTERN.search(clause):
        return True
    return _PREFIX_CONTEXT_MARKER_PATTERN.search(clause) is not None


def _strip_prefix_clause_intro(clause: str) -> str:
    clause = clause.strip()
    patterns = (
        r"^(?:我)?\s*(?:只需要输出|只需要|只需|只输出|只看|重点分析|重点看|重点关注|关注|只分析|查看前缀|指定前缀|看看|查看)\s*",
        r"(?i)^(?:focus\s+on|focus)\s*",
    )
    for pattern in patterns:
        clause = re.sub(pattern, "", clause)
    return clause.strip()


def normalize_prefix_token(token: str) -> str | None:
    cleaned = token.strip().strip("`'\"()[]{}")
    if not cleaned:
        return None
    cleaned = re.sub(r"(?i)\b(?:only|need|output|prefix|key|keys|details?)\b", " ", cleaned)
    cleaned = cleaned.replace("前缀", " ").replace("键", " ").replace("详情", " ").replace("分析", " ")
    cleaned = cleaned.strip().strip(":")
    if not cleaned:
        return None
    cleaned = _WHITESPACE_PATTERN.sub("", cleaned)
    if not _PREFIX_CANDIDATE_PATTERN.fullmatch(cleaned):
        return None
    if not re.search(r"[A-Za-z]", cleaned):
        return None
    if cleaned.lower() in _PREFIX_TOKEN_STOPWORDS:
        return None
    if cleaned.endswith(":*"):
        return cleaned
    if "*" in cleaned:
        return None
    return f"{cleaned}:*"


def normalize_requested_prefixes(tokens: object) -> tuple[str, ...]:
    normalized_tokens: list[str] = []
    seen: set[str] = set()

    for token in tokens:
        if not isinstance(token, str):
            continue
        normalized = normalize_prefix_token(token)
        if normalized is None or normalized in seen:
            continue
        seen.add(normalized)
        normalized_tokens.append(normalized)

    return tuple(normalized_tokens)


def _normalize_focus_prefix_token(token: str) -> str | None:
    return normalize_prefix_token(token)


def _extract_generic_top_n_from_clause(clause: str) -> int | None:
    if _SUMMARY_TOP_N_SKIP_PATTERN.search(clause) and not re.search(
        r"(?i)\bkey\b|键|prefix|前缀|string|hash|list|set|zset|stream|other",
        clause,
    ):
        return None

    for pattern in _GENERIC_TOP_PATTERNS:
        for match in pattern.finditer(clause):
            if _generic_top_match_is_section_specific(clause, match.start()):
                continue
            count = int(match.group("count"))
            if _is_valid_top_n(count):
                return count
    return None


def _generic_top_match_is_section_specific(clause: str, match_start: int) -> bool:
    prefix = clause[:match_start].rstrip().lower()
    return any(prefix.endswith(section) for section in _SECTION_ALIAS_TO_TOP_KEY)


def _expand_generic_top_n(count: int) -> dict[str, int]:
    return {
        "prefix_top": count,
        "top_big_keys": count,
        "string_big_keys": count,
        "hash_big_keys": count,
        "list_big_keys": count,
        "set_big_keys": count,
        "zset_big_keys": count,
        "stream_big_keys": count,
        "other_big_keys": count,
        "focused_prefix_top_keys": count,
    }


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

    if raw_path.startswith('"') or raw_path.startswith("'"):
        quote = raw_path[0]
        end_quote = raw_path.rfind(quote)
        if end_quote > 0:
            raw_path = raw_path[1:end_quote].strip()
    else:
        trailing = re.search(
            r"(?:\s*,\s*|\s+)(?:and|but|then|also|plus|email|send|and\s+email|and\s+send|并且|并|然后|再|同时|此外|另外|但|但是|不过|然而|可是|而是|却)\b.*$",
            raw_path,
            flags=re.IGNORECASE,
        )
        if trailing is not None:
            raw_path = raw_path[: trailing.start()].rstrip()

    if not raw_path:
        return None

    return Path(raw_path).expanduser()
