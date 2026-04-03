from pathlib import Path

from dba_assistant.application.prompt_parser import normalize_raw_request


def test_normalize_raw_request_extracts_runtime_inputs_and_secrets() -> None:
    request = normalize_raw_request(
        "Use password abc123 to inspect Redis 10.0.0.8:6380 db 2 and give me a summary",
        default_output_mode="summary",
    )

    assert request.raw_prompt == (
        "Use password abc123 to inspect Redis 10.0.0.8:6380 db 2 and give me a summary"
    )
    assert request.prompt == "Use to inspect Redis 10.0.0.8:6380 db 2 and give me a summary"
    assert request.runtime_inputs.redis_host == "10.0.0.8"
    assert request.runtime_inputs.redis_port == 6380
    assert request.runtime_inputs.redis_db == 2
    assert request.runtime_inputs.output_mode == "summary"
    assert request.secrets.redis_password == "abc123"


def test_normalize_raw_request_uses_default_output_mode_when_unspecified() -> None:
    request = normalize_raw_request(
        "Inspect Redis 10.0.0.9:6379",
        default_output_mode="summary",
    )

    assert request.runtime_inputs.redis_host == "10.0.0.9"
    assert request.runtime_inputs.redis_port == 6379
    assert request.runtime_inputs.output_mode == "summary"
    assert request.secrets.redis_password is None
    assert request.prompt == "Inspect Redis 10.0.0.9:6379"


def test_normalize_raw_request_threads_explicit_input_paths() -> None:
    source = Path("/tmp/dump.rdb")

    request = normalize_raw_request(
        "analyze this rdb",
        default_output_mode="summary",
        input_paths=[source],
    )

    assert request.runtime_inputs.input_paths == (source,)


def test_normalize_raw_request_prefers_explicit_use_as_password_form() -> None:
    request = normalize_raw_request(
        "Use abc123 as the redis password and inspect Redis 10.0.0.8:6379",
        default_output_mode="summary",
    )

    assert request.secrets.redis_password == "abc123"
    assert request.runtime_inputs.redis_host == "10.0.0.8"
    assert request.runtime_inputs.redis_port == 6379
    assert "abc123" not in request.prompt


def test_normalize_raw_request_allows_colon_and_dot_in_password_without_host_confusion() -> None:
    request = normalize_raw_request(
        "Use password abc:123.def to inspect Redis 10.0.0.8:6379 and give me a summary",
        default_output_mode="summary",
    )

    assert request.secrets.redis_password == "abc:123.def"
    assert request.runtime_inputs.redis_host == "10.0.0.8"
    assert request.runtime_inputs.redis_port == 6379
    assert "abc:123.def" not in request.prompt


def test_normalize_raw_request_extracts_password_from_chinese_password_phrase() -> None:
    request = normalize_raw_request(
        "使用密码 abc123 检查 Redis 10.0.0.8:6379 并给我 summary",
        default_output_mode="summary",
    )

    assert request.secrets.redis_password == "abc123"
    assert request.runtime_inputs.redis_host == "10.0.0.8"
    assert request.runtime_inputs.redis_port == 6379
    assert "abc123" not in request.prompt


def test_normalize_raw_request_extracts_password_from_chinese_as_password_phrase() -> None:
    request = normalize_raw_request(
        "使用 abc123 作为 Redis 密码，检查 Redis 10.0.0.8:6379",
        default_output_mode="summary",
    )

    assert request.secrets.redis_password == "abc123"
    assert request.runtime_inputs.redis_host == "10.0.0.8"
    assert request.runtime_inputs.redis_port == 6379
    assert "abc123" not in request.prompt


def test_normalize_raw_request_extracts_task_2_profile_overrides() -> None:
    request = normalize_raw_request(
        "按通用profile分析这个rdb，重点看order:*前缀，prefix top 30，hash top 20，top 8",
        default_output_mode="summary",
    )

    assert request.rdb_overrides.profile_name == "generic"
    assert request.rdb_overrides.focus_prefixes == ("order:*",)
    assert request.rdb_overrides.top_n == {
        "prefix_top": 30,
        "hash_big_keys": 20,
        "top_big_keys": 8,
    }


def test_normalize_raw_request_extracts_rcs_profile_from_task_2_form() -> None:
    request = normalize_raw_request(
        "按rcs profile分析这批rdb",
        default_output_mode="summary",
    )

    assert request.rdb_overrides.profile_name == "rcs"
    assert request.rdb_overrides.focus_prefixes == ()
    assert request.rdb_overrides.top_n == {}


def test_normalize_raw_request_extracts_profile_from_explicit_with_form() -> None:
    request = normalize_raw_request(
        "analyze this rdb with the generic profile",
        default_output_mode="summary",
    )

    assert request.rdb_overrides.profile_name == "generic"


def test_normalize_raw_request_ignores_negated_profile_phrases() -> None:
    for prompt in (
        "请不要按 generic profile 分析这个rdb",
        "不要用 generic profile 分析这个rdb",
        "禁用 generic profile",
    ):
        request = normalize_raw_request(prompt, default_output_mode="summary")
        assert request.rdb_overrides.profile_name is None


def test_normalize_raw_request_ignores_long_distance_negated_profile_phrases() -> None:
    request = normalize_raw_request(
        "please do not under any circumstances use the generic profile",
        default_output_mode="summary",
    )

    assert request.rdb_overrides.profile_name is None


def test_normalize_raw_request_honors_later_profile_correction() -> None:
    request = normalize_raw_request(
        "do not use the generic profile, but use the rcs profile",
        default_output_mode="summary",
    )

    assert request.rdb_overrides.profile_name == "rcs"


def test_normalize_raw_request_ignores_profile_false_positives() -> None:
    for prompt in (
        "analyze the nongeneric profile for this RDB",
        "analyze the srcs profile for this RDB",
        "analyze the genericprofile for this RDB",
        "analyze the non-generic profile for this RDB",
        "analyze the custom-generic profile for this RDB",
        "analyze the custom generic profile for this RDB",
        "analyze a very generic profile for this RDB",
        "按非rcs profile分析这个rdb",
    ):
        request = normalize_raw_request(prompt, default_output_mode="summary")
        assert request.rdb_overrides.profile_name is None


def test_normalize_raw_request_extracts_only_prefix_token_from_chinese_context() -> None:
    request = normalize_raw_request(
        "按通用profile分析这个rdb，重点看order:*前缀",
        default_output_mode="summary",
    )

    assert request.rdb_overrides.focus_prefixes == ("order:*",)
    assert request.rdb_overrides.profile_name == "generic"


def test_normalize_raw_request_extracts_multiple_prefixes_from_one_explicit_instruction() -> None:
    request = normalize_raw_request(
        "按通用profile分析这个rdb，重点看 loan:* 和 cis:* 前缀",
        default_output_mode="summary",
    )

    assert request.rdb_overrides.focus_prefixes == ("loan:*", "cis:*")


def test_normalize_raw_request_does_not_treat_bare_prefix_token_as_override() -> None:
    request = normalize_raw_request(
        "I saw order:* in the logs, but this is just narration about the dataset",
        default_output_mode="summary",
    )

    assert request.rdb_overrides.focus_prefixes == ()


def test_normalize_raw_request_does_not_switch_output_mode_from_standalone_tokens() -> None:
    request = normalize_raw_request(
        "Please give me a report and a summary of this Redis analysis",
        default_output_mode="compact",
    )

    assert request.runtime_inputs.output_mode == "compact"


def test_normalize_raw_request_does_not_treat_summary_top_n_phrases_as_rdb_overrides() -> None:
    for prompt in (
        "include the top 8 findings in the summary",
        "报告里只写 top 8 个结论",
    ):
        request = normalize_raw_request(prompt, default_output_mode="summary")
        assert request.rdb_overrides.top_n == {}


def test_normalize_raw_request_ignores_out_of_range_top_n_overrides() -> None:
    request = normalize_raw_request(
        "按通用profile分析这个rdb，prefix top 0，hash top 101，top 9999",
        default_output_mode="summary",
    )

    assert request.rdb_overrides.top_n == {}


def test_normalize_raw_request_extracts_docx_report_request() -> None:
    request = normalize_raw_request(
        "按 rcs profile 分析这个 rdb，输出 docx，到 /tmp/rcs.docx",
        default_output_mode="summary",
    )

    assert request.rdb_overrides.profile_name == "rcs"
    assert request.runtime_inputs.output_mode == "report"
    assert request.runtime_inputs.report_format == "docx"
    assert request.runtime_inputs.output_path == Path("/tmp/rcs.docx")


def test_normalize_raw_request_does_not_enable_report_mode_for_negated_output_request() -> None:
    request = normalize_raw_request(
        "do not output docx",
        default_output_mode="summary",
    )

    assert request.runtime_inputs.output_mode == "summary"
    assert request.runtime_inputs.report_format is None


def test_normalize_raw_request_honors_later_output_correction() -> None:
    request = normalize_raw_request(
        "output summary, actually output docx",
        default_output_mode="summary",
    )

    assert request.runtime_inputs.output_mode == "report"
    assert request.runtime_inputs.report_format == "docx"


def test_normalize_raw_request_does_not_treat_connection_path_as_output_destination() -> None:
    request = normalize_raw_request(
        "连接到 /tmp/redis.sock 并输出 summary",
        default_output_mode="summary",
    )

    assert request.runtime_inputs.output_path is None


def test_normalize_raw_request_keeps_summary_output_mode_for_summary_intent() -> None:
    request = normalize_raw_request(
        "按 generic profile 分析这个 rdb，输出 summary，到 /tmp/rcs.txt",
        default_output_mode="report",
    )

    assert request.runtime_inputs.output_mode == "summary"
    assert request.runtime_inputs.report_format is None
    assert request.runtime_inputs.output_path == Path("/tmp/rcs.txt")


def test_normalize_raw_request_expands_home_tilde_output_path() -> None:
    request = normalize_raw_request(
        "按 rcs profile 分析这个 rdb，输出 docx，到 ~/rcs.docx",
        default_output_mode="summary",
    )

    assert request.runtime_inputs.output_path == Path("~/rcs.docx").expanduser()


def test_normalize_raw_request_extracts_output_path_with_spaces() -> None:
    request = normalize_raw_request(
        "output docx to /tmp/my report.docx",
        default_output_mode="summary",
    )

    assert request.runtime_inputs.output_path == Path("/tmp/my report.docx")


def test_normalize_raw_request_extracts_output_path_from_bare_filename() -> None:
    request = normalize_raw_request(
        "输出 docx 到 report.docx",
        default_output_mode="summary",
    )

    assert request.runtime_inputs.output_path == Path("report.docx")


def test_normalize_raw_request_extracts_quoted_output_path() -> None:
    request = normalize_raw_request(
        '输出 docx 到 "report final.docx"',
        default_output_mode="summary",
    )

    assert request.runtime_inputs.output_path == Path("report final.docx")


def test_normalize_raw_request_extracts_output_path_from_trailing_instruction_text() -> None:
    request = normalize_raw_request(
        "output docx to /tmp/a.docx and email it",
        default_output_mode="summary",
    )

    assert request.runtime_inputs.output_path == Path("/tmp/a.docx")


def test_normalize_raw_request_extracts_mysql_routing_hint() -> None:
    request = normalize_raw_request(
        "按 generic profile 分析这个 rdb，使用 mysql 路径并输出 summary",
        default_output_mode="summary",
    )

    assert request.rdb_overrides.route_name == "legacy_sql_pipeline"


def test_normalize_raw_request_does_not_route_on_bare_mysql_token() -> None:
    for prompt in (
        "按 generic profile 分析这个 rdb，连接 mysql 数据库并输出 summary",
        "按 generic profile 分析这个 rdb，mysql host 是 127.0.0.1",
        "按 generic profile 分析这个 rdb，mysql 用户名是 root",
    ):
        request = normalize_raw_request(prompt, default_output_mode="summary")
        assert request.rdb_overrides.route_name is None


def test_normalize_raw_request_ignores_negated_mysql_route_phrases() -> None:
    for prompt in (
        "不要 mysql route",
        "do not use mysql route",
        "不要走 mysql 路径",
        "do not use the mysql route",
        "don't use the mysql route",
    ):
        request = normalize_raw_request(prompt, default_output_mode="summary")
        assert request.rdb_overrides.route_name is None


def test_normalize_raw_request_ignores_long_distance_negated_mysql_route_phrases() -> None:
    request = normalize_raw_request(
        "please do not under any circumstances use the mysql route",
        default_output_mode="summary",
    )

    assert request.rdb_overrides.route_name is None


def test_normalize_raw_request_honors_later_mysql_route_correction() -> None:
    request = normalize_raw_request(
        "do not use the mysql route, but use the mysql route now",
        default_output_mode="summary",
    )

    assert request.rdb_overrides.route_name == "legacy_sql_pipeline"
