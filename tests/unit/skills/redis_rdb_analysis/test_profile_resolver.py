import pytest

from dba_assistant.application.prompt_parser import normalize_raw_request
from dba_assistant.skills.redis_rdb_analysis.profile_resolver import resolve_profile


@pytest.mark.parametrize(
    ("prompt", "profile_name", "focus_prefixes", "top_n"),
    [
        (
            "按通用profile分析这个rdb，重点看order:*前缀，prefix top 30，hash top 20，top 8",
            "generic",
            ("order:*",),
            {"prefix_top": 30, "hash_big_keys": 20, "top_big_keys": 8},
        ),
        (
            "按rcs profile分析这批rdb",
            "rcs",
            (),
            {},
        ),
    ],
)
def test_normalize_raw_request_extracts_task_2_profile_overrides(
    prompt: str,
    profile_name: str,
    focus_prefixes: tuple[str, ...],
    top_n: dict[str, int],
) -> None:
    request = normalize_raw_request(prompt, default_output_mode="summary")

    assert request.rdb_overrides.profile_name == profile_name
    assert request.rdb_overrides.focus_prefixes == focus_prefixes
    assert request.rdb_overrides.top_n == top_n


@pytest.mark.parametrize(
    "prompt",
    [
        "analyze the nongeneric profile for this RDB",
        "analyze the srcs profile for this RDB",
        "analyze the genericprofile for this RDB",
    ],
)
def test_normalize_raw_request_ignores_profile_substrings_inside_larger_words(
    prompt: str,
) -> None:
    request = normalize_raw_request(prompt, default_output_mode="summary")

    assert request.rdb_overrides.profile_name is None


def test_normalize_raw_request_extracts_only_prefix_token_from_chinese_context() -> None:
    request = normalize_raw_request(
        "按通用profile分析这个rdb，重点看order:*前缀",
        default_output_mode="summary",
    )

    assert request.rdb_overrides.profile_name == "generic"
    assert request.rdb_overrides.focus_prefixes == ("order:*",)


def test_resolve_generic_profile_merges_defaults_with_prompt_overrides() -> None:
    request = normalize_raw_request(
        "analyze this rdb with the generic profile and focus on loan:* and cis:*; prefix top 30; set top 5",
        default_output_mode="summary",
    )

    profile = resolve_profile("generic", request.rdb_overrides)

    assert profile.name == "generic"
    assert "executive_summary" in profile.sections
    assert "expiration_summary" in profile.sections
    assert profile.focus_prefixes[:2] == ("loan:*", "cis:*")
    assert profile.top_n["prefix_top"] == 30
    assert profile.top_n["set_big_keys"] == 5


def test_resolve_rcs_profile_keeps_rcs_specific_sections() -> None:
    request = normalize_raw_request(
        "按 rcs profile 分析这批 RDB",
        default_output_mode="summary",
    )

    profile = resolve_profile("rcs", request.rdb_overrides)

    assert "background" in profile.sections
    assert "loan_prefix_detail" in profile.sections
    assert "loan:*" in profile.focus_prefixes
