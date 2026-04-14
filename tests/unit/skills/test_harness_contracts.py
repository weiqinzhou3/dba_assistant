from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SYSTEM_PROMPT = ROOT / "src" / "dba_assistant" / "prompts" / "unified_system_prompt.md"
RDB_SKILL = ROOT / "skills" / "redis-rdb-analysis" / "SKILL.md"
INSPECTION_SKILL = ROOT / "skills" / "redis-inspection-report" / "SKILL.md"
PROMPT_PARSER = ROOT / "src" / "dba_assistant" / "application" / "prompt_parser.py"


def test_unified_system_prompt_is_generic_and_not_rdb_or_inspection_sop() -> None:
    prompt = SYSTEM_PROMPT.read_text(encoding="utf-8").lower()

    assert "redis rdb" not in prompt
    assert "inspect_local_rdb" not in prompt
    assert "stage_local_rdb_to_mysql" not in prompt
    assert "analyze_local_rdb_stream" not in prompt
    assert "discover_remote_rdb" not in prompt
    assert "redis_inspection_report" not in prompt
    assert "last 30 days" not in prompt
    assert "1 gb" not in prompt
    assert "mysql-backed" not in prompt
    assert "automated file inspection" not in prompt

    assert "skills" in prompt
    assert "skill contract" in prompt
    assert "secure runtime context" in prompt
    assert "artifact contract" in prompt


def test_rdb_skill_owns_analysis_strategy_and_artifact_contract() -> None:
    skill = RDB_SKILL.read_text(encoding="utf-8").lower()

    for required in (
        "inspect_local_rdb",
        "analyze_local_rdb_stream",
        "stage_local_rdb_to_mysql",
        "analyze_staged_rdb",
        "larger than 1 gb",
        "refuses mysql",
        "immediately proceed",
        "discover_remote_rdb",
        "ensure_remote_rdb_snapshot",
        "fetch_remote_rdb_via_ssh",
        "output_mode='report'",
        "report_format='docx'",
        "generated docx artifact path",
        "runtime interrupt",
        "do not invent",
    ):
        assert required in skill


def test_inspection_skill_owns_defaults_parameters_and_output_contract() -> None:
    skill = INSPECTION_SKILL.read_text(encoding="utf-8").lower()

    for required in (
        "redis 巡检",
        "offline evidence inspection",
        "live read-only inspection",
        "log_time_window_days",
        "log_start_time",
        "log_end_time",
        "default to the last 30 days",
        "/tmp/dba_assistant_redis_inspection_<timestamp>.docx",
        "do not require the user to provide output_path",
        "docx mode must generate",
        "artifact path",
        "approval-aware",
        "missing evidence",
        "deterministic evidence reduction",
        "llm semantic review",
        "normal persistence",
        "cluster-level merged issues",
        "detailed risk items",
        "do not invent",
    ):
        assert required in skill


def test_prompt_parser_declares_non_semantic_boundary() -> None:
    source = PROMPT_PARSER.read_text(encoding="utf-8").lower()

    assert "not an llm parser" in source
    assert "business semantics" in source
    assert "log_time_window_days" not in source
    assert "report_format" not in source
    assert "output_path" not in source
    assert "path_mode" not in source
