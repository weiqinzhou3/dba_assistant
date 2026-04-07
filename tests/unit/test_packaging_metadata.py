from pathlib import Path
import tomllib


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_pyproject_declares_src_layout_and_console_entrypoint() -> None:
    document = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert document["tool"]["setuptools"]["package-dir"] == {"": "src"}
    assert document["tool"]["setuptools"]["packages"]["find"]["where"] == ["src"]
    assert document["tool"]["setuptools"]["packages"]["find"]["include"] == [
        "dba_assistant",
        "dba_assistant.*",
    ]
    assert document["project"]["scripts"]["dba-assistant"] == "dba_assistant.cli:main"
    assert (REPO_ROOT / "src" / "dba_assistant" / "__init__.py").exists()
    assert (REPO_ROOT / "src" / "dba_assistant" / "cli.py").exists()


def test_repository_contains_bootstrap_and_doctor_entrypoints() -> None:
    assert (REPO_ROOT / "scripts" / "bootstrap.sh").exists()
    assert (REPO_ROOT / "scripts" / "doctor.py").exists()
    assert (REPO_ROOT / "scripts" / "run_cli.sh").exists()
    assert (REPO_ROOT / "scripts" / "smoke_install.sh").exists()
