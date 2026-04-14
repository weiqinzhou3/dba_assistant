"""Tests for dynamic profile availability."""

from dba_assistant.capabilities.redis_rdb_analysis.profile_resolver import available_profile_names


def test_available_profile_names_returns_at_least_generic_and_rcs() -> None:
    names = available_profile_names()
    assert "generic" in names
    assert "rcs" in names
