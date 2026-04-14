from pathlib import Path

from dba_assistant.application.prompt_parser import (
    normalize_raw_request,
    normalize_requested_prefixes,
)


def test_normalize_raw_request_extracts_redis_secret_without_materializing_runtime_target() -> None:
    request = normalize_raw_request(
        "Use password abc123 to inspect Redis 10.0.0.8:6380 db 2 and give me a summary",
        default_output_mode="summary",
    )

    assert request.runtime_inputs.redis_host is None
    assert request.runtime_inputs.input_kind is None
    assert request.runtime_inputs.output_mode == "summary"
    assert request.secrets.redis_password == "abc123"
    assert "abc123" not in request.prompt


def test_normalize_raw_request_threads_explicit_input_paths() -> None:
    source = Path("/tmp/dump.rdb")

    request = normalize_raw_request(
        "analyze this rdb",
        default_output_mode="summary",
        input_paths=[source],
    )

    assert request.runtime_inputs.input_paths == (source,)
    assert request.runtime_inputs.input_kind == "local_rdb"


def test_normalize_raw_request_does_not_extract_prompt_only_paths() -> None:
    request = normalize_raw_request(
        "分析 /data/a.rdb 和 /data/b.rdb，重点看 TTL 和大 key",
        default_output_mode="summary",
    )

    assert request.runtime_inputs.input_paths == ()
    assert request.runtime_inputs.input_kind is None


def test_normalize_raw_request_extracts_mysql_password_only() -> None:
    request = normalize_raw_request(
        "请帮我分析本地rdb文件。rdb文件在：/tmp/dump.rdb。"
        "MySQL信息如下：192.168.23.176:3306，用户名root，密码Root@1234!，"
        "使用数据库rcs，表名叫rdb。",
        default_output_mode="summary",
    )

    assert request.runtime_inputs.mysql_host is None
    assert request.runtime_inputs.mysql_query is None
    assert request.secrets.mysql_password == "Root@1234!"
    assert "Root@1234!" not in request.prompt
    assert request.rdb_overrides.profile_name is None
    assert request.rdb_overrides.focus_prefixes == ()
    assert request.rdb_overrides.top_n == {}


def test_normalize_raw_request_extracts_mysql_query_without_promoting_runtime_target() -> None:
    request = normalize_raw_request(
        'mysql 192.168.23.176:3306，用户名 root，密码 Root@1234!，执行 "select * from preparsed_keys"',
        default_output_mode="summary",
    )

    assert request.runtime_inputs.mysql_host is None
    assert request.runtime_inputs.mysql_query is None
    assert request.runtime_inputs.input_kind is None
    assert request.secrets.mysql_password == "Root@1234!"


def test_normalize_raw_request_extracts_ssh_secret_without_materializing_ssh_runtime_fields() -> None:
    request = normalize_raw_request(
        "ssh 192.168.23.54:2222 root/ssh-secret，帮我拉取 Redis 10.0.0.8:6379 的最新快照",
        default_output_mode="summary",
    )

    assert request.runtime_inputs.ssh_host is None
    assert request.runtime_inputs.ssh_username is None
    assert request.secrets.ssh_password == "ssh-secret"
    assert "ssh-secret" not in request.prompt


def test_normalize_raw_request_extracts_multiple_scoped_secrets_without_endpoint_parsing() -> None:
    request = normalize_raw_request(
        "请你连接到远端Redis，帮我抓取一份最新的rdb文件，并分析。"
        "Redis信息如下：192.168.23.54:6379，密码是123456，"
        "ssh信息如下：192.168.23.54:22 用户名是root，密码是root。",
        default_output_mode="summary",
    )

    assert request.runtime_inputs.redis_host is None
    assert request.runtime_inputs.ssh_host is None
    assert request.runtime_inputs.require_fresh_rdb_snapshot is False
    assert request.secrets.redis_password == "123456"
    assert request.secrets.ssh_password == "root"


def test_normalize_raw_request_does_not_infer_docx_from_prompt_prose() -> None:
    request = normalize_raw_request(
        "按 rcs profile 分析这个 rdb，输出 docx，到 /tmp/rcs.docx",
        default_output_mode="summary",
    )

    assert request.runtime_inputs.output_mode == "summary"
    assert request.runtime_inputs.report_format is None
    assert request.runtime_inputs.output_path is None


def test_normalize_requested_prefixes_normalizes_and_deduplicates() -> None:
    assert normalize_requested_prefixes(["order:*", "order:*", "  session:*  "]) == (
        "order:*",
        "session:*",
    )


def test_normalize_requested_prefixes_skips_control_tokens() -> None:
    assert normalize_requested_prefixes(["docx", "top10", "summary", "cache:*"]) == (
        "cache:*",
    )
