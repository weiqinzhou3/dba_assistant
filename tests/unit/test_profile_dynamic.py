"""Tests for dynamic profile name resolution in prompt_parser (WI-7)."""
from dba_assistant.application.prompt_parser import normalize_raw_request
from dba_assistant.capabilities.redis_rdb_analysis.profile_resolver import available_profile_names


def test_available_profile_names_returns_at_least_generic_and_rcs() -> None:
    names = available_profile_names()
    assert "generic" in names
    assert "rcs" in names


def test_prompt_parser_recognizes_generic_profile() -> None:
    request = normalize_raw_request(
        "analyze this rdb with generic profile",
        default_output_mode="summary",
    )
    assert request.rdb_overrides.profile_name == "generic"


def test_prompt_parser_recognizes_rcs_profile() -> None:
    request = normalize_raw_request(
        "use rcs profile to analyze this",
        default_output_mode="summary",
    )
    assert request.rdb_overrides.profile_name == "rcs"


def test_prompt_parser_recognizes_dynamically_added_profile(tmp_path, monkeypatch) -> None:
    """If a new profile YAML is added, the parser should recognize it."""
    import dba_assistant.application.prompt_parser as parser_module

    # Rebuild the alternation with an extra profile name
    monkeypatch.setattr(
        parser_module,
        "_PROFILE_ALT",
        "generic|rcs|custom_test",
    )
    import re
    monkeypatch.setattr(
        parser_module,
        "_WITH_PROFILE_PATTERN",
        re.compile(rf"(?i)\bwith\s+(?:the\s+)?(?P<profile>{parser_module._PROFILE_ALT})\s+profile(?![a-z0-9_])"),
    )
    monkeypatch.setattr(
        parser_module,
        "_USE_PROFILE_PATTERN",
        re.compile(rf"(?i)\b(?:use|using|choose|select)\s+(?:the\s+)?(?P<profile>{parser_module._PROFILE_ALT})\s+profile(?![a-z0-9_])"),
    )

    request = normalize_raw_request(
        "use custom_test profile to analyze",
        default_output_mode="summary",
    )
    assert request.rdb_overrides.profile_name == "custom_test"
