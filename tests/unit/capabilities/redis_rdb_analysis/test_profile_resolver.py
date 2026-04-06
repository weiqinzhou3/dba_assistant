from dba_assistant.application.request_models import RdbOverrides
from dba_assistant.capabilities.redis_rdb_analysis.profile_resolver import resolve_profile


def test_resolve_generic_profile_exposes_expected_default_sections() -> None:
    profile = resolve_profile("generic", RdbOverrides())

    assert profile.name == "generic"
    assert "executive_summary" in profile.sections
    assert "expiration_summary" in profile.sections
    assert "top_string_keys" in profile.sections
    assert "top_stream_keys" in profile.sections
    assert "top_keys_by_type" not in profile.sections
    assert profile.top_n["prefix_top"] == 100
    assert profile.top_n["top_big_keys"] == 100
    assert profile.top_n["string_big_keys"] == 100


def test_resolve_generic_profile_merges_defaults_with_prompt_overrides() -> None:
    profile = resolve_profile(
        "generic",
        RdbOverrides(
            focus_prefixes=("loan:*", "cis:*"),
            top_n={"prefix_top": 30, "stream_big_keys": 5},
        ),
    )

    assert profile.name == "generic"
    assert "executive_summary" in profile.sections
    assert "expiration_summary" in profile.sections
    assert profile.focus_prefixes[:2] == ("loan:*", "cis:*")
    assert profile.top_n["prefix_top"] == 30
    assert profile.top_n["stream_big_keys"] == 5


def test_resolve_rcs_profile_keeps_rcs_specific_sections() -> None:
    profile = resolve_profile("rcs", RdbOverrides())

    assert "background" in profile.sections
    assert "focused_prefix_analysis" in profile.sections
    assert "loan:*" in profile.focus_prefixes


def test_resolve_rcs_profile_uses_defaults_when_prompt_does_not_specify_prefixes() -> None:
    profile = resolve_profile("rcs", RdbOverrides())

    assert profile.focus_prefixes == ("loan:*", "cis:*", "tag:*")


def test_resolve_rcs_profile_prefers_explicit_prompt_prefixes_over_profile_defaults() -> None:
    profile = resolve_profile(
        "rcs",
        RdbOverrides(focus_prefixes=("mq:*", "order:*")),
    )

    assert profile.focus_prefixes == ("mq:*", "order:*")
