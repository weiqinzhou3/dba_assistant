# Local Development Setup

This repository uses a `src/` layout and a `dba-assistant` console entrypoint. The stable local workflow is to bootstrap the repository-owned `.venv` and always run the CLI through that environment.

## First-Time Setup

Create or repair the local virtual environment:

```bash
./scripts/bootstrap.sh
```

What it does:

- creates `.venv` when missing
- upgrades `pip`, `setuptools`, and `wheel`
- installs the project with `pip install -e .`
- verifies `python -c "import dba_assistant"`
- verifies `dba-assistant --help`
- runs the repository doctor check

If you also need development extras such as `pytest`:

```bash
./scripts/bootstrap.sh --dev
```

If you want a clean rebuild:

```bash
./scripts/bootstrap.sh --recreate
```

## Day-to-Day Commands

Run doctor against the current `.venv`:

```bash
.venv/bin/python scripts/doctor.py --strict
```

Run the CLI without activating another environment:

```bash
./scripts/run_cli.sh ask "analyze the local rdb"
```

## Do I Need to Reinstall After Code Changes?

- Pure Python source changes under `src/dba_assistant/` usually do not require a reinstall once the environment is healthy.
- If you change packaging metadata, dependencies, or the virtual environment looks inconsistent, rerun `./scripts/bootstrap.sh`.
- If the environment keeps acting suspicious, use `./scripts/bootstrap.sh --recreate`.

## How to Verify the Install

These three checks should pass inside `.venv`:

```bash
.venv/bin/python -c "import dba_assistant; print(dba_assistant.__file__)"
.venv/bin/dba-assistant --help
.venv/bin/python scripts/doctor.py --strict
```

## Recovering from `ModuleNotFoundError: dba_assistant`

Symptoms may look like this:

- `dba-assistant` exists under `.venv/bin/`
- `pip show dba-assistant` says the package is installed
- `python -c "import dba_assistant"` still fails

That means the current environment has package metadata or a stale console script, but the package path is not actually active for the interpreter you are using.

Recovery steps:

1. Rebuild the environment:

```bash
./scripts/bootstrap.sh --recreate
```

2. Inspect the environment:

```bash
.venv/bin/python scripts/doctor.py --strict
```

3. If you only need a temporary unblock, run directly from `src/`:

```bash
PYTHONPATH=src python -m dba_assistant.cli --help
```

## Temporary Bypass

If packaging is broken and you need to run the CLI immediately, bypass installation and import directly from `src/`:

```bash
PYTHONPATH=src python -m dba_assistant.cli ask "analyze the local rdb"
```

This is a fallback only. The preferred path is to repair `.venv` with `./scripts/bootstrap.sh`.
