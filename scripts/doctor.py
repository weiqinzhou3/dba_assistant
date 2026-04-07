#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import site
import subprocess
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "dba_assistant"
DIST_NAME = "dba-assistant"


def _current_venv() -> Path | None:
    if sys.prefix == sys.base_prefix:
        return None
    return Path(sys.prefix)


def _site_packages() -> list[Path]:
    return [Path(path) for path in site.getsitepackages() if path]


def _pip_show() -> dict[str, Any]:
    result = subprocess.run(
        [sys.executable, "-m", "pip", "show", DIST_NAME],
        capture_output=True,
        text=True,
        check=False,
    )
    info: dict[str, str] = {}
    if result.returncode == 0:
        for line in result.stdout.splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            info[key.strip()] = value.strip()
    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "info": info,
        "stderr": result.stderr.strip(),
    }


def _read_shebang(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        first_line = path.read_text(encoding="utf-8").splitlines()[0]
    except Exception:
        return None
    if not first_line.startswith("#!"):
        return None
    return first_line[2:].strip()


def _console_script_path(current_venv: Path | None) -> Path | None:
    if current_venv is not None:
        candidate = current_venv / "bin" / "dba-assistant"
        if candidate.exists():
            return candidate
    resolved = shutil.which("dba-assistant")
    if resolved is None:
        return None
    return Path(resolved).resolve()


def collect_diagnostics(expect_venv: Path | None) -> dict[str, Any]:
    current_venv = _current_venv()
    console_script = _console_script_path(current_venv)
    pip_show = _pip_show()
    import_ok = False
    import_path = None
    import_error = None

    try:
        module = __import__(PACKAGE_NAME)
    except Exception as exc:
        import_error = repr(exc)
    else:
        import_ok = True
        import_path = str(Path(module.__file__).resolve())

    site_packages = _site_packages()
    editable_pths = []
    repair_pths = []
    dist_infos = []
    for site_package in site_packages:
        editable_pths.extend(str(path) for path in site_package.glob("__editable__.dba_assistant-*.pth"))
        repair_pths.extend(str(path) for path in site_package.glob("dba_assistant_repo_src.pth"))
        dist_infos.extend(str(path) for path in site_package.glob("dba_assistant-*.dist-info"))

    console_python = _read_shebang(console_script) if console_script is not None else None
    repo_src = str(REPO_ROOT / "src")
    diagnostics: dict[str, Any] = {
        "current_python": sys.executable,
        "current_venv": None if current_venv is None else str(current_venv),
        "expected_venv": None if expect_venv is None else str(expect_venv),
        "repo_root": str(REPO_ROOT),
        "repo_src": repo_src,
        "repo_src_on_sys_path": repo_src in sys.path,
        "import_ok": import_ok,
        "import_path": import_path,
        "import_error": import_error,
        "pip_show_ok": pip_show["ok"],
        "pip_show_info": pip_show["info"],
        "pip_show_stderr": pip_show["stderr"],
        "console_script": None if console_script is None else str(console_script),
        "console_script_python": console_python,
        "console_script_matches_current_python": console_python == sys.executable if console_python else False,
        "console_script_in_current_venv": (
            console_python.startswith(str(current_venv)) if console_python and current_venv is not None else False
        ),
        "editable_pth_files": editable_pths,
        "repair_pth_files": repair_pths,
        "dist_info_dirs": dist_infos,
        "site_packages": [str(path) for path in site_packages],
        "issues": [],
        "notes": [],
    }

    issues: list[str] = diagnostics["issues"]
    notes: list[str] = diagnostics["notes"]
    if expect_venv is not None and current_venv != expect_venv.resolve():
        issues.append("Current interpreter is not running inside the expected virtual environment.")
    if not diagnostics["pip_show_ok"]:
        issues.append("pip metadata for dba-assistant is missing in the current interpreter.")
    if diagnostics["pip_show_ok"] and not diagnostics["import_ok"]:
        issues.append(
            "Package metadata exists but import still fails. This usually means the editable install path is not active or the environment is damaged."
        )
    if console_script is None:
        issues.append("The dba-assistant console script is missing from the current environment.")
    elif not diagnostics["console_script_matches_current_python"]:
        issues.append("The dba-assistant console script points at a different python interpreter.")
    if diagnostics["editable_pth_files"] and not diagnostics["repo_src_on_sys_path"]:
        issues.append("Editable install metadata exists, but the repository src path is not active on sys.path.")
    if diagnostics["repair_pth_files"]:
        notes.append("A repository-managed repair .pth file is present for this environment.")

    return diagnostics


def _print_text_report(diagnostics: dict[str, Any]) -> None:
    lines = [
        f"python: {diagnostics['current_python']}",
        f"venv: {diagnostics['current_venv'] or '<none>'}",
        f"expected venv: {diagnostics['expected_venv'] or '<not set>'}",
        f"import dba_assistant: {'ok' if diagnostics['import_ok'] else 'failed'}",
        f"pip show dba-assistant: {'ok' if diagnostics['pip_show_ok'] else 'failed'}",
        f"console script: {diagnostics['console_script'] or '<missing>'}",
        f"console script python: {diagnostics['console_script_python'] or '<unknown>'}",
        f"repo src on sys.path: {diagnostics['repo_src_on_sys_path']}",
        f"editable .pth files: {len(diagnostics['editable_pth_files'])}",
        f"repair .pth files: {len(diagnostics['repair_pth_files'])}",
    ]
    for line in lines:
        print(line)
    if diagnostics["issues"]:
        print("issues:")
        for item in diagnostics["issues"]:
            print(f"- {item}")
    else:
        print("issues:")
        print("- Environment looks healthy.")
    if diagnostics["notes"]:
        print("notes:")
        for item in diagnostics["notes"]:
            print(f"- {item}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Diagnose local DBA Assistant installation health.")
    parser.add_argument("--strict", action="store_true", help="exit non-zero when the environment looks unhealthy")
    parser.add_argument("--json", action="store_true", help="emit diagnostics as JSON")
    parser.add_argument("--expect-venv", default=None, help="expected virtualenv path")
    args = parser.parse_args(argv)

    expect_venv = None if args.expect_venv is None else Path(args.expect_venv).resolve()
    diagnostics = collect_diagnostics(expect_venv)
    if args.json:
        print(json.dumps(diagnostics, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_text_report(diagnostics)

    if args.strict and diagnostics["issues"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
