from dba_assistant.skills_runtime.assets import (
    load_numbered_outline_titles,
    load_skill_json_asset,
    load_skill_text_asset,
    load_skill_yaml_asset,
    skill_package_dir,
)


def test_skill_package_dir_resolves_inspection_skill() -> None:
    path = skill_package_dir("redis-inspection-report")

    assert path.name == "redis-inspection-report"
    assert (path / "SKILL.md").exists()


def test_shared_asset_loader_reads_inspection_json_yaml_and_text_assets() -> None:
    schema = load_skill_json_asset("redis-inspection-report", "assets/log_issue_schema.json")
    tables = load_skill_yaml_asset("redis-inspection-report", "assets/table_schemas.yaml")
    outline_text = load_skill_text_asset("redis-inspection-report", "assets/report_outline.md")
    titles = load_numbered_outline_titles("redis-inspection-report", "assets/report_outline.md")

    assert schema["properties"]["issues"]["type"] == "array"
    assert tables["problem_overview"]["columns"][0] == "集群"
    assert "问题概览与整改优先级" in outline_text
    assert titles[2] == "问题概览与整改优先级"
