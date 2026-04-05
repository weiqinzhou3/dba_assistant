from dba_assistant.deep_agent_integration.runtime_support import get_skill_sources


def test_get_skill_sources_points_to_repo_root_skills_directory() -> None:
    assert get_skill_sources() == ["/skills"]
