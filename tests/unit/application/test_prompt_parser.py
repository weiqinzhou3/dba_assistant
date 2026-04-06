from pathlib import Path

from dba_assistant.application.prompt_parser import (
    normalize_raw_request,
    normalize_requested_prefixes,
)


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
    assert request.runtime_inputs.input_kind == "remote_redis"
    assert request.runtime_inputs.output_mode == "summary"
    assert request.secrets.redis_password == "abc123"


def test_normalize_raw_request_uses_default_output_mode_when_unspecified() -> None:
    request = normalize_raw_request(
        "Inspect Redis 10.0.0.9:6379",
        default_output_mode="summary",
    )

    assert request.runtime_inputs.redis_host == "10.0.0.9"
    assert request.runtime_inputs.redis_port == 6379
    assert request.runtime_inputs.input_kind == "remote_redis"
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


def test_normalize_raw_request_extracts_single_local_rdb_path_from_prompt() -> None:
    request = normalize_raw_request(
        "分析 /data/dump.rdb，重点看 TTL 和大 key",
        default_output_mode="summary",
    )

    assert request.runtime_inputs.input_paths == (Path("/data/dump.rdb"),)
    assert request.runtime_inputs.input_kind == "local_rdb"


def test_normalize_raw_request_extracts_multiple_local_rdb_paths_from_prompt() -> None:
    request = normalize_raw_request(
        "分析 /data/a.rdb 和 /data/b.rdb，重点看 TTL 和大 key",
        default_output_mode="summary",
    )

    assert request.runtime_inputs.input_paths == (
        Path("/data/a.rdb"),
        Path("/data/b.rdb"),
    )
    assert request.runtime_inputs.input_kind == "local_rdb"


def test_normalize_raw_request_extracts_multiple_local_rdb_paths_from_english_prompt() -> None:
    request = normalize_raw_request(
        "Analyze /tmp/one.rdb and /tmp/two.rdb, focus on TTL distribution",
        default_output_mode="summary",
    )

    assert request.runtime_inputs.input_paths == (
        Path("/tmp/one.rdb"),
        Path("/tmp/two.rdb"),
    )
    assert request.runtime_inputs.input_kind == "local_rdb"


def test_normalize_raw_request_prefers_explicit_input_paths_over_prompt_paths() -> None:
    explicit = Path("/tmp/explicit.rdb")
    request = normalize_raw_request(
        "分析 /data/a.rdb 和 /data/b.rdb",
        default_output_mode="summary",
        input_paths=[explicit],
    )

    assert request.runtime_inputs.input_paths == (explicit,)
    assert request.runtime_inputs.input_kind == "local_rdb"


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


def test_normalize_raw_request_extracts_redis_password_from_remote_redis_natural_language() -> None:
    request = normalize_raw_request(
        "请帮我分析远端Redis，192.168.23.54:6379，密码是123456，如果有必要请拉取一份最新的rdb文件。",
        default_output_mode="summary",
    )

    assert request.runtime_inputs.redis_host == "192.168.23.54"
    assert request.runtime_inputs.redis_port == 6379
    assert request.runtime_inputs.input_kind == "remote_redis"
    assert request.secrets.redis_password == "123456"
    assert "123456" not in request.prompt


def test_normalize_raw_request_keeps_local_rdb_and_mysql_context_separate() -> None:
    request = normalize_raw_request(
        "请帮我分析本地rdb文件，传入MySQL中分析。rdb文件在：/tmp/dump.rdb ， "
        "MySQL信息如下：192.168.23.176:3306，用户名root，密码Root@1234! ，"
        "使用数据库rcs，表名叫rdb 吧。",
        default_output_mode="summary",
    )

    assert request.runtime_inputs.input_paths == (Path("/tmp/dump.rdb"),)
    assert request.runtime_inputs.mysql_host == "192.168.23.176"
    assert request.runtime_inputs.mysql_port == 3306
    assert request.runtime_inputs.mysql_user == "root"
    assert request.runtime_inputs.mysql_database == "rcs"
    assert request.runtime_inputs.mysql_table == "rdb"
    assert request.runtime_inputs.input_kind == "local_rdb"
    assert request.runtime_inputs.redis_host is None
    assert request.runtime_inputs.remote_rdb_path is None


def test_normalize_raw_request_extracts_task_2_profile_overrides() -> None:
    request = normalize_raw_request(
        "按通用profile分析这个rdb，重点看order:*前缀，prefix top 30，hash top 20，top 8",
        default_output_mode="summary",
    )

    assert request.rdb_overrides.profile_name == "generic"
    assert request.rdb_overrides.focus_prefixes == ("order:*",)
    assert request.rdb_overrides.top_n == {
        "prefix_top": 30,
        "top_big_keys": 8,
        "string_big_keys": 8,
        "hash_big_keys": 20,
        "list_big_keys": 8,
        "set_big_keys": 8,
        "zset_big_keys": 8,
        "stream_big_keys": 8,
        "other_big_keys": 8,
        "focused_prefix_top_keys": 8,
    }


def test_normalize_raw_request_extracts_rcs_profile_from_task_2_form() -> None:
    request = normalize_raw_request(
        "按rcs profile分析这批rdb",
        default_output_mode="summary",
    )

    assert request.rdb_overrides.profile_name == "rcs"
    assert request.rdb_overrides.focus_prefixes == ()
    assert request.rdb_overrides.top_n == {}


def test_normalize_raw_request_extracts_rcs_profile_from_natural_chinese_aliases() -> None:
    for prompt in (
        "使用 rcs profile 分析这个 rdb",
        "按照 rcs profile 进行分析",
        "指定 rcs profile，导出 docx",
        "按 rcs 模板分析本地 rdb",
        "用 rcs 模板分析",
        "使用 rcs 模板分析",
        "用 rcs 报告输出",
        "按 rcs 报告风格输出",
        "用 rcs 报告风格分析",
        "使用 rcs 配置分析",
    ):
        request = normalize_raw_request(prompt, default_output_mode="summary")
        assert request.rdb_overrides.profile_name == "rcs"


def test_normalize_raw_request_extracts_generic_profile_from_natural_chinese_aliases() -> None:
    for prompt in (
        "用通用模板分析",
        "使用通用报告风格",
        "按通用配置输出报告",
    ):
        request = normalize_raw_request(prompt, default_output_mode="summary")
        assert request.rdb_overrides.profile_name == "generic"


def test_normalize_raw_request_does_not_treat_environment_mention_as_profile_override() -> None:
    request = normalize_raw_request(
        "我在 rcs 环境里，帮我分析这个 rdb",
        default_output_mode="summary",
    )

    assert request.rdb_overrides.profile_name is None


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


def test_normalize_raw_request_does_not_treat_not_only_as_profile_negation() -> None:
    request = normalize_raw_request(
        "not only use the generic profile",
        default_output_mode="summary",
    )

    assert request.rdb_overrides.profile_name == "generic"


def test_normalize_raw_request_honors_later_profile_correction() -> None:
    request = normalize_raw_request(
        "do not use the generic profile, but use the rcs profile",
        default_output_mode="summary",
    )

    assert request.rdb_overrides.profile_name == "rcs"


def test_normalize_raw_request_prefers_later_textual_profile_match() -> None:
    request = normalize_raw_request(
        "按 rcs profile analyze this rdb with the generic profile",
        default_output_mode="summary",
    )

    assert request.rdb_overrides.profile_name == "generic"


def test_normalize_raw_request_prefers_later_textual_profile_match_in_english() -> None:
    request = normalize_raw_request(
        "use the generic profile, then analyze with the rcs profile",
        default_output_mode="summary",
    )

    assert request.rdb_overrides.profile_name == "rcs"


def test_normalize_raw_request_keeps_existing_profile_when_later_negation_targets_other_profile() -> None:
    request = normalize_raw_request(
        "use the generic profile, but do not use the rcs profile",
        default_output_mode="summary",
    )

    assert request.rdb_overrides.profile_name == "generic"


def test_normalize_raw_request_prefers_later_generic_profile_match_after_rcs() -> None:
    request = normalize_raw_request(
        "按 rcs profile analyze this rdb with the generic profile",
        default_output_mode="summary",
    )

    assert request.rdb_overrides.profile_name == "generic"


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


def test_normalize_raw_request_does_not_treat_incidental_prefix_mention_as_focus_override() -> None:
    request = normalize_raw_request(
        "analyze this rdb with the generic profile and mention that order:* is common",
        default_output_mode="summary",
    )

    assert request.rdb_overrides.focus_prefixes == ()


def test_normalize_raw_request_does_not_treat_inspect_narration_as_focus_override() -> None:
    request = normalize_raw_request(
        "inspect this rdb and mention order:* is common",
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


def test_normalize_raw_request_extracts_generic_top_n_from_compact_chinese_and_english_forms() -> None:
    expected = {
        "prefix_top": 10,
        "top_big_keys": 10,
        "string_big_keys": 10,
        "hash_big_keys": 10,
        "list_big_keys": 10,
        "set_big_keys": 10,
        "zset_big_keys": 10,
        "stream_big_keys": 10,
        "other_big_keys": 10,
        "focused_prefix_top_keys": 10,
    }
    for prompt in (
        "top 10",
        "top10",
        "前10",
        "前 10",
        "只看 top 10",
        "只输出前 10 个",
        "展示前10个",
        "top 10 个 key",
        "top 10 的报告",
    ):
        request = normalize_raw_request(prompt, default_output_mode="summary")
        assert request.rdb_overrides.top_n == expected


def test_normalize_raw_request_extracts_section_specific_top_n_and_prefers_them_over_generic_top_n() -> None:
    request = normalize_raw_request(
        "top 10, string top 20, 前缀 top 30",
        default_output_mode="summary",
    )

    assert request.rdb_overrides.top_n == {
        "prefix_top": 30,
        "top_big_keys": 10,
        "string_big_keys": 20,
        "hash_big_keys": 10,
        "list_big_keys": 10,
        "set_big_keys": 10,
        "zset_big_keys": 10,
        "stream_big_keys": 10,
        "other_big_keys": 10,
        "focused_prefix_top_keys": 10,
    }


def test_normalize_raw_request_extracts_prefix_specific_top_n_from_chinese_prompt() -> None:
    request = normalize_raw_request(
        "使用 rcs profile，前缀 top 10",
        default_output_mode="summary",
    )

    assert request.rdb_overrides.top_n == {"prefix_top": 10}


def test_normalize_raw_request_extracts_requested_focus_prefixes_as_explicit_override() -> None:
    request = normalize_raw_request(
        "使用 rcs profile，但只看 order:* 和 mq:*，不要用默认前缀",
        default_output_mode="summary",
    )

    assert request.rdb_overrides.profile_name == "rcs"
    assert request.rdb_overrides.focus_prefixes == ("order:*", "mq:*")


def test_normalize_raw_request_detects_focus_only_for_prefix_keys() -> None:
    request = normalize_raw_request(
        "只需要输出前缀为tag的key，其他都不需要",
        default_output_mode="summary",
    )

    assert request.rdb_overrides.focus_only is True
    assert request.rdb_overrides.focus_prefixes == ("tag:*",)


def test_normalize_raw_request_detects_focus_only_for_natural_prefix_key_request() -> None:
    request = normalize_raw_request(
        "我只需要signin的key,其他分析结果都不需要",
        default_output_mode="summary",
    )

    assert request.rdb_overrides.focus_only is True
    assert request.rdb_overrides.focus_prefixes == ("signin:*",)


def test_normalize_raw_request_normalizes_all_requested_prefix_key_forms() -> None:
    cases = {
        "只看 order 和 mq 的 key 详情": ("order:*", "mq:*"),
        "重点看 user:profile 和 session:data": ("user:profile:*", "session:data:*"),
        "只分析 device:token 的 key": ("device:token:*",),
        "关注 loan 和 cis 的 key": ("loan:*", "cis:*"),
        "前缀为 tag 的 key": ("tag:*",),
        "指定前缀 user:profile:*": ("user:profile:*",),
        "只需要输出前缀为 tag:* 的 key": ("tag:*",),
    }

    for prompt, expected in cases.items():
        request = normalize_raw_request(prompt, default_output_mode="summary")
        assert request.rdb_overrides.focus_prefixes == expected


def test_normalize_requested_prefixes_applies_generic_suffix_completion_and_keeps_order() -> None:
    assert normalize_requested_prefixes(
        (
            "tag",
            "store",
            "signin",
            "order",
            "mq",
            "loan",
            "cis",
            "user:profile",
            "session:data",
            "device:token",
            "tag:*",
            "store",
        )
    ) == (
        "tag:*",
        "store:*",
        "signin:*",
        "order:*",
        "mq:*",
        "loan:*",
        "cis:*",
        "user:profile:*",
        "session:data:*",
        "device:token:*",
    )


def test_normalize_raw_request_extracts_multiple_prefixes_from_explicit_prefix_phrases() -> None:
    cases = {
        "前缀为tag和前缀为store": ("tag:*", "store:*"),
        "前缀是signin和store": ("signin:*", "store:*"),
        "重点分析两个前缀，一个是signin，一个是store": ("signin:*", "store:*"),
        "关注user:profile和session:data": ("user:profile:*", "session:data:*"),
    }

    for prompt, expected in cases.items():
        request = normalize_raw_request(prompt, default_output_mode="summary")
        assert request.rdb_overrides.focus_prefixes == expected


def test_normalize_raw_request_extracts_rcs_profile_focus_prefixes_without_switching_to_focus_only() -> None:
    request = normalize_raw_request(
        "使用 rcs profile，重点分析 tag 和 store",
        default_output_mode="summary",
    )

    assert request.rdb_overrides.profile_name == "rcs"
    assert request.rdb_overrides.focus_prefixes == ("tag:*", "store:*")
    assert request.rdb_overrides.focus_only is False


def test_normalize_raw_request_extracts_generic_top_n_even_when_combined_with_focus_clause() -> None:
    request = normalize_raw_request(
        "top 10 重点分析 tag 和 store",
        default_output_mode="summary",
    )

    assert request.rdb_overrides.focus_prefixes == ("tag:*", "store:*")
    assert request.rdb_overrides.top_n == {
        "prefix_top": 10,
        "top_big_keys": 10,
        "string_big_keys": 10,
        "hash_big_keys": 10,
        "list_big_keys": 10,
        "set_big_keys": 10,
        "zset_big_keys": 10,
        "stream_big_keys": 10,
        "other_big_keys": 10,
        "focused_prefix_top_keys": 10,
    }


def test_normalize_raw_request_ignores_out_of_range_top_n_overrides() -> None:
    request = normalize_raw_request(
        "按通用profile分析这个rdb，prefix top 0，hash top 101，top 9999",
        default_output_mode="summary",
    )

    assert request.rdb_overrides.top_n == {
        "hash_big_keys": 101,
    }


def test_normalize_raw_request_extracts_docx_report_request() -> None:
    request = normalize_raw_request(
        "按 rcs profile 分析这个 rdb，输出 docx，到 /tmp/rcs.docx",
        default_output_mode="summary",
    )

    assert request.rdb_overrides.profile_name == "rcs"
    assert request.runtime_inputs.output_mode == "report"
    assert request.runtime_inputs.report_format == "docx"
    assert request.runtime_inputs.output_path == Path("/tmp/rcs.docx")


def test_normalize_raw_request_treats_word_alias_as_docx() -> None:
    request = normalize_raw_request(
        "请分析这个 rdb，输出为docx/word文件给我",
        default_output_mode="summary",
    )

    assert request.runtime_inputs.output_mode == "report"
    assert request.runtime_inputs.report_format == "docx"
    assert request.runtime_inputs.output_path is None


def test_normalize_raw_request_extracts_word_document_request_as_docx() -> None:
    request = normalize_raw_request(
        "导出为word文档",
        default_output_mode="summary",
    )

    assert request.runtime_inputs.output_mode == "report"
    assert request.runtime_inputs.report_format == "docx"


def test_normalize_raw_request_extracts_output_word_as_docx() -> None:
    request = normalize_raw_request(
        "输出word",
        default_output_mode="summary",
    )

    assert request.runtime_inputs.output_mode == "report"
    assert request.runtime_inputs.report_format == "docx"


def test_normalize_raw_request_does_not_enable_report_mode_for_negated_output_request() -> None:
    request = normalize_raw_request(
        "do not output docx",
        default_output_mode="summary",
    )

    assert request.runtime_inputs.output_mode == "summary"
    assert request.runtime_inputs.report_format is None


def test_normalize_raw_request_does_not_treat_not_only_as_output_negation() -> None:
    request = normalize_raw_request(
        "not only output docx",
        default_output_mode="summary",
    )

    assert request.runtime_inputs.output_mode == "report"
    assert request.runtime_inputs.report_format == "docx"


def test_normalize_raw_request_honors_later_output_correction() -> None:
    request = normalize_raw_request(
        "output summary, actually output docx",
        default_output_mode="summary",
    )

    assert request.runtime_inputs.output_mode == "report"
    assert request.runtime_inputs.report_format == "docx"


def test_normalize_raw_request_keeps_earlier_output_when_later_clause_negates_other_format() -> None:
    request = normalize_raw_request(
        "output docx to /tmp/a.docx but do not output pdf",
        default_output_mode="summary",
    )

    assert request.runtime_inputs.output_mode == "report"
    assert request.runtime_inputs.report_format == "docx"
    assert request.runtime_inputs.output_path == Path("/tmp/a.docx")


def test_normalize_raw_request_clears_output_when_later_clause_negates_same_format() -> None:
    request = normalize_raw_request(
        "output docx, but do not output docx",
        default_output_mode="summary",
    )

    assert request.runtime_inputs.output_mode == "summary"
    assert request.runtime_inputs.report_format is None
    assert request.runtime_inputs.output_path is None


def test_normalize_raw_request_drops_output_path_for_negated_output_clause() -> None:
    request = normalize_raw_request(
        "do not output docx to /tmp/nope.docx",
        default_output_mode="summary",
    )

    assert request.runtime_inputs.output_mode == "summary"
    assert request.runtime_inputs.report_format is None
    assert request.runtime_inputs.output_path is None


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


def test_normalize_raw_request_strips_trailing_comma_before_followup_clause_from_output_path() -> None:
    request = normalize_raw_request(
        "output docx to /tmp/a.docx, then output summary",
        default_output_mode="summary",
    )

    assert request.runtime_inputs.output_mode == "summary"
    assert request.runtime_inputs.report_format is None
    assert request.runtime_inputs.output_path is None


def test_normalize_raw_request_resets_output_path_when_later_output_format_has_no_destination() -> None:
    request = normalize_raw_request(
        "output pdf to /tmp/a.pdf, then output docx",
        default_output_mode="summary",
    )

    assert request.runtime_inputs.output_mode == "report"
    assert request.runtime_inputs.report_format == "docx"
    assert request.runtime_inputs.output_path is None


def test_normalize_raw_request_extracts_mysql_routing_hint() -> None:
    request = normalize_raw_request(
        "按 generic profile 分析这个 rdb，使用 mysql 路径并输出 summary",
        default_output_mode="summary",
    )

    assert request.rdb_overrides.route_name == "database_backed_analysis"


def test_normalize_raw_request_extracts_mysql_connection_and_table_from_prompt() -> None:
    request = normalize_raw_request(
        "从 MySQL 192.168.0.10:3306，用户名 root，密码 secret123，数据库 dba，表 redis_rows 读取预处理数据并分析",
        default_output_mode="summary",
    )

    assert request.runtime_inputs.mysql_host == "192.168.0.10"
    assert request.runtime_inputs.mysql_port == 3306
    assert request.runtime_inputs.mysql_user == "root"
    assert request.runtime_inputs.mysql_database == "dba"
    assert request.runtime_inputs.mysql_table == "redis_rows"
    assert request.runtime_inputs.mysql_query is None
    assert request.runtime_inputs.input_kind == "preparsed_mysql"
    assert request.secrets.mysql_password == "secret123"
    assert request.secrets.redis_password is None
    assert request.runtime_inputs.redis_host is None


def test_normalize_raw_request_extracts_mysql_query_from_prompt() -> None:
    request = normalize_raw_request(
        '从 MySQL 192.168.0.10:3306 用户名 root 密码 secret123 数据库 dba，查询 "SELECT * FROM redis_rows LIMIT 10" 并分析',
        default_output_mode="summary",
    )

    assert request.runtime_inputs.mysql_host == "192.168.0.10"
    assert request.runtime_inputs.mysql_port == 3306
    assert request.runtime_inputs.mysql_user == "root"
    assert request.runtime_inputs.mysql_database == "dba"
    assert request.runtime_inputs.mysql_table is None
    assert request.runtime_inputs.mysql_query == "SELECT * FROM redis_rows LIMIT 10"
    assert request.runtime_inputs.input_kind == "preparsed_mysql"
    assert request.secrets.mysql_password == "secret123"


def test_normalize_raw_request_extracts_mysql_connection_and_table_from_english_prompt() -> None:
    request = normalize_raw_request(
        "Use MySQL 10.0.0.8:3306 user root password secret123 database dba table redis_rows to analyze preparsed dataset",
        default_output_mode="summary",
    )

    assert request.runtime_inputs.mysql_host == "10.0.0.8"
    assert request.runtime_inputs.mysql_port == 3306
    assert request.runtime_inputs.mysql_user == "root"
    assert request.runtime_inputs.mysql_database == "dba"
    assert request.runtime_inputs.mysql_table == "redis_rows"
    assert request.runtime_inputs.mysql_query is None
    assert request.runtime_inputs.input_kind == "preparsed_mysql"
    assert request.secrets.mysql_password == "secret123"


def test_normalize_raw_request_extracts_unquoted_mysql_query_and_database_alias() -> None:
    request = normalize_raw_request(
        "从 MySQL 192.168.1.10:3306 的 dba 库里执行 select * from redis_rows where key_name like 'user:%'，并做分析",
        default_output_mode="summary",
    )

    assert request.runtime_inputs.mysql_host == "192.168.1.10"
    assert request.runtime_inputs.mysql_port == 3306
    assert request.runtime_inputs.mysql_database == "dba"
    assert request.runtime_inputs.mysql_table is None
    assert request.runtime_inputs.mysql_query == "select * from redis_rows where key_name like 'user:%'"
    assert request.runtime_inputs.input_kind == "preparsed_mysql"


def test_normalize_raw_request_extracts_both_redis_and_mysql_targets_from_prompt() -> None:
    request = normalize_raw_request(
        "分析 redis.example:6379 的最新 rdb，并写入 MySQL 192.168.0.10:3306 用户名 root 密码 secret123 数据库 dba",
        default_output_mode="summary",
    )

    assert request.runtime_inputs.redis_host == "redis.example"
    assert request.runtime_inputs.redis_port == 6379
    assert request.runtime_inputs.input_kind == "remote_redis"
    assert request.runtime_inputs.mysql_host == "192.168.0.10"
    assert request.runtime_inputs.mysql_port == 3306
    assert request.runtime_inputs.mysql_user == "root"
    assert request.runtime_inputs.mysql_database == "dba"
    assert request.secrets.mysql_password == "secret123"


def test_normalize_raw_request_extracts_ssh_fields_from_chinese_prompt() -> None:
    request = normalize_raw_request(
        "分析 Redis 192.168.23.54:6379。SSH信息如下：主机地址 192.168.23.54，用户名是 root，密码也是 root",
        default_output_mode="summary",
    )

    assert request.runtime_inputs.redis_host == "192.168.23.54"
    assert request.runtime_inputs.ssh_host == "192.168.23.54"
    assert request.runtime_inputs.ssh_port == 22
    assert request.runtime_inputs.ssh_username == "root"
    assert request.secrets.ssh_password == "root"


def test_normalize_raw_request_extracts_ssh_fields_from_compact_prompt() -> None:
    request = normalize_raw_request(
        "通过 SSH 192.168.23.54 root/root 拉取远端 RDB，并分析 Redis 192.168.23.54:6379",
        default_output_mode="summary",
    )

    assert request.runtime_inputs.ssh_host == "192.168.23.54"
    assert request.runtime_inputs.ssh_port == 22
    assert request.runtime_inputs.ssh_username == "root"
    assert request.secrets.ssh_password == "root"


def test_normalize_raw_request_extracts_ssh_fields_from_english_prompt() -> None:
    request = normalize_raw_request(
        "Analyze Redis 192.168.23.54:6379 and ssh host 192.168.23.54 user root password root",
        default_output_mode="summary",
    )

    assert request.runtime_inputs.ssh_host == "192.168.23.54"
    assert request.runtime_inputs.ssh_port == 22
    assert request.runtime_inputs.ssh_username == "root"
    assert request.secrets.ssh_password == "root"


def test_normalize_raw_request_keeps_redis_and_ssh_passwords_separate() -> None:
    request = normalize_raw_request(
        "Redis 192.168.23.54:6379 密码是 123456。SSH信息如下：主机地址 192.168.23.54，用户名是 root，密码也是 root。如果有必要请拉取一份最新的 rdb 文件。",
        default_output_mode="summary",
    )

    assert request.runtime_inputs.redis_host == "192.168.23.54"
    assert request.secrets.redis_password == "123456"
    assert request.runtime_inputs.ssh_host == "192.168.23.54"
    assert request.runtime_inputs.ssh_username == "root"
    assert request.secrets.ssh_password == "root"
    assert request.runtime_inputs.require_fresh_rdb_snapshot is True


def test_normalize_raw_request_extracts_remote_rdb_path_as_override_in_remote_context() -> None:
    request = normalize_raw_request(
        "请帮我分析远端Redis，192.168.23.54:6379，密码是123456。SSH信息如下：主机地址 192.168.23.54，用户名是root，密码也是root。rdb文件在 /data/redis/data/dump.rdb",
        default_output_mode="summary",
    )

    assert request.runtime_inputs.redis_host == "192.168.23.54"
    assert request.runtime_inputs.remote_rdb_path == "/data/redis/data/dump.rdb"
    assert request.runtime_inputs.remote_rdb_path_source == "user_override"
    assert request.runtime_inputs.input_paths == ()
    assert request.runtime_inputs.input_kind == "remote_redis"


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


def test_normalize_raw_request_does_not_treat_not_only_as_mysql_route_negation() -> None:
    request = normalize_raw_request(
        "not only use the mysql route",
        default_output_mode="summary",
    )

    assert request.rdb_overrides.route_name == "database_backed_analysis"


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

    assert request.rdb_overrides.route_name == "database_backed_analysis"


def test_normalize_raw_request_defaults_report_language_to_chinese() -> None:
    request = normalize_raw_request(
        "分析这个 rdb，输出 summary",
        default_output_mode="summary",
    )

    assert request.runtime_inputs.report_language == "zh-CN"


def test_normalize_raw_request_extracts_explicit_english_report_language() -> None:
    request = normalize_raw_request(
        "Analyze this rdb and output the report in English",
        default_output_mode="summary",
    )

    assert request.runtime_inputs.report_language == "en-US"


def test_normalize_raw_request_extracts_explicit_chinese_report_language() -> None:
    request = normalize_raw_request(
        "请分析这个 rdb，输出中文版报告",
        default_output_mode="summary",
    )

    assert request.runtime_inputs.report_language == "zh-CN"
