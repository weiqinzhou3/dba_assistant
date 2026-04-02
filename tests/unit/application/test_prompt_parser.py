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
