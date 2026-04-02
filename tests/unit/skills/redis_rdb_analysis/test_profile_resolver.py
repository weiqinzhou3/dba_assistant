import pytest

from dba_assistant.application.prompt_parser import normalize_raw_request
from dba_assistant.skills.redis_rdb_analysis.profile_resolver import resolve_profile


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


def test_normalize_raw_request_extracts_generic_profile_and_bounded_overrides() -> None:
    request = normalize_raw_request(
        "按通用 profile 分析这个 RDB，重点看 order:* 前缀，prefix top 30，hash top 20，top 8",
        default_output_mode="summary",
    )

    assert request.rdb_overrides.profile_name == "generic"
    assert request.rdb_overrides.focus_prefixes == ("order:*",)
    assert request.rdb_overrides.top_n["prefix_top"] == 30
    assert request.rdb_overrides.top_n["hash_big_keys"] == 20
    assert request.rdb_overrides.top_n["top_big_keys"] == 8


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
