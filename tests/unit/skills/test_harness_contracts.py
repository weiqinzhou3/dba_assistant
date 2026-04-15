from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SYSTEM_PROMPT = ROOT / "src" / "dba_assistant" / "prompts" / "unified_system_prompt.md"
RDB_SKILL = ROOT / "skills" / "redis-rdb-analysis" / "SKILL.md"
INSPECTION_SKILL = ROOT / "skills" / "redis-inspection-report" / "SKILL.md"
PROMPT_PARSER = ROOT / "src" / "dba_assistant" / "application" / "prompt_parser.py"
INSPECTION_PACKAGE = ROOT / "skills" / "redis-inspection-report"
RDB_PACKAGE = ROOT / "skills" / "redis-rdb-analysis"


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
        "configured `paths.artifact_dir`",
        "dba_assistant_redis_inspection_<timestamp>.docx",
        "do not require the user to provide output_path",
        "docx mode must generate",
        "artifact path",
        "approval-aware",
        "missing evidence",
        "deterministic evidence reduction",
        "collect_offline_inspection_dataset",
        "dataset_handle",
        "avoid re-parsing",
        "review_redis_log_candidates",
        "directly consume the candidate payload",
        "must not use generic filesystem tools",
        "render_redis_inspection_report",
        "llm semantic review",
        "normal persistence",
        "cluster-level merged issues",
        "detailed risk items",
        "references/log_judgement_guide.md",
        "assets/log_issue_schema.json",
        "do not invent",
    ):
        assert required in skill


def test_inspection_skill_package_contains_references_assets_and_scripts() -> None:
    required_files = {
        "references/grouping_policy.md": ("cluster", "do not guess", "chapter 3", "chapter 9"),
        "references/log_judgement_guide.md": ("normal aof", "rdb copy-on-write", "oom", "fork"),
        "references/severity_policy.md": ("llm", "deterministic", "critical", "high"),
        "references/report_writing_guide.md": ("artifact", "cluster", "chapter"),
        "assets/report_outline.md": ("第三章", "第九章", "docx"),
        "assets/table_schemas.yaml": ("problem_overview", "detailed_risk_items"),
        "assets/log_issue_schema.json": ("is_anomalous", "merge_key", "supporting_samples"),
        "assets/cluster_merge_schema.json": ("affected_nodes", "merged_issues"),
        "assets/style_rules.md": ("highlight", "heading"),
        "scripts/readonly_redis_probe_examples.sh": ("redis-cli", "readonly"),
        "scripts/ssh_log_read_examples.sh": ("ssh", "tail", "read-only"),
    }

    for relative_path, expected_terms in required_files.items():
        path = INSPECTION_PACKAGE / relative_path
        assert path.exists(), relative_path
        text = path.read_text(encoding="utf-8").lower()
        for term in expected_terms:
            assert term in text, f"{relative_path} missing {term}"


def test_rdb_skill_package_contains_references_assets_and_scripts() -> None:
    required_files = {
        "references/strategy_policy.md": ("inspect_local_rdb", "direct stream", "mysql-backed"),
        "references/mysql_staging_policy.md": ("larger than 1 gb", "refuses mysql", "approval"),
        "references/docx_contract.md": ("docx", "artifact path", "output_path"),
        "assets/report_outline.md": ("memory", "prefix", "big key"),
        "assets/output_contract.json": ("artifact_path", "report_format", "docx"),
        "scripts/mysql_queries.sql": ("select", "limit", "staging"),
    }

    for relative_path, expected_terms in required_files.items():
        path = RDB_PACKAGE / relative_path
        assert path.exists(), relative_path
        text = path.read_text(encoding="utf-8").lower()
        for term in expected_terms:
            assert term in text, f"{relative_path} missing {term}"


def test_prompt_parser_declares_non_semantic_boundary() -> None:
    source = PROMPT_PARSER.read_text(encoding="utf-8").lower()

    assert "not an llm parser" in source
    assert "business semantics" in source
    assert "log_time_window_days" not in source
    assert "report_format" not in source
    assert "output_path" not in source
    assert "path_mode" not in source
