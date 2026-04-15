from pathlib import Path


def test_production_code_does_not_embed_tmp_as_runtime_output_or_work_dir() -> None:
    project_root = Path(__file__).resolve().parents[2]
    source_root = project_root / "src" / "dba_assistant"
    offenders: list[str] = []

    for path in source_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if 'Path("/tmp")' in text or 'dir="/tmp"' in text or '"/tmp/dba_assistant' in text:
            offenders.append(str(path.relative_to(project_root)))

    assert offenders == []
