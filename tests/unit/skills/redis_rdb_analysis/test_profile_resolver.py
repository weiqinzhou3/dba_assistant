from dba_assistant.application.request_models import RdbOverrides
from dba_assistant.skills.redis_rdb_analysis.profile_resolver import resolve_profile


def test_resolve_generic_profile_exposes_expected_default_sections() -> None:
    profile = resolve_profile("generic", RdbOverrides())

    assert profile.name == "generic"
    assert "executive_summary" in profile.sections
    assert "expiration_summary" in profile.sections
    assert profile.top_n["prefix_top"] == 20


def test_resolve_generic_profile_merges_defaults_with_prompt_overrides() -> None:
    profile = resolve_profile(
        "generic",
        RdbOverrides(
            focus_prefixes=("loan:*", "cis:*"),
            top_n={"prefix_top": 30, "set_big_keys": 5},
        ),
    )

    assert profile.name == "generic"
    assert "executive_summary" in profile.sections
    assert "expiration_summary" in profile.sections
    assert profile.focus_prefixes[:2] == ("loan:*", "cis:*")
    assert profile.top_n["prefix_top"] == 30
    assert profile.top_n["set_big_keys"] == 5


def test_resolve_rcs_profile_keeps_rcs_specific_sections() -> None:
    profile = resolve_profile("rcs", RdbOverrides())

    assert "background" in profile.sections
    assert "loan_prefix_detail" in profile.sections
    assert "loan:*" in profile.focus_prefixes
