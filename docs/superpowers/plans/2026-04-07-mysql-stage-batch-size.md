# MySQL Stage Batch Size Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make MySQL-backed RDB staging batch size configurable from `config/config.yaml`, overridable from CLI, and reflected consistently in execution, approval text, metadata, and file logs.

**Architecture:** Add one repository-owned runtime setting, thread it through `InterfaceRequest -> RuntimeInputs -> orchestrator -> PathAMySQLBackedCollector`, and remove implicit reliance on the hard-coded default from the MySQL-backed route. Keep one effective batch-size value per request so writes, approval messaging, metadata, and observability all report the same number.

**Tech Stack:** Python, argparse, dataclasses, pytest, repository observability JSONL logging

---

### Task 1: Add failing tests for config and CLI override

**Files:**
- Modify: `tests/unit/deep_agent_integration/test_config.py`
- Modify: `tests/unit/test_cli.py`
- Modify: `tests/unit/interface/test_adapter.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_load_app_config_reads_mysql_stage_batch_size(...):
    assert config.runtime.mysql_stage_batch_size == 5000


def test_cli_ask_threads_mysql_stage_batch_size_to_interface_request(...):
    assert req.mysql_stage_batch_size == 4000


def test_cli_rejects_non_positive_mysql_stage_batch_size(...):
    with pytest.raises(SystemExit):
        cli.main(["ask", "x", "--mysql-stage-batch-size", "0"])


def test_handle_request_prefers_cli_mysql_stage_batch_size_over_config(...):
    assert captured["normalized"].runtime_inputs.mysql_stage_batch_size == 4096
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest -q tests/unit/deep_agent_integration/test_config.py tests/unit/test_cli.py tests/unit/interface/test_adapter.py`
Expected: FAIL because runtime config, CLI parser, and adapter override path do not yet support `mysql_stage_batch_size`.

- [ ] **Step 3: Implement minimal config and CLI plumbing**

```python
class RuntimeConfig:
    mysql_stage_batch_size: int = 2000
```

```python
ask_parser.add_argument("--mysql-stage-batch-size", default=None, type=int)
```

```python
@dataclass(frozen=True)
class InterfaceRequest:
    mysql_stage_batch_size: int | None = None
```

```python
runtime_inputs = replace(
    runtime_inputs,
    mysql_stage_batch_size=request.mysql_stage_batch_size,
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest -q tests/unit/deep_agent_integration/test_config.py tests/unit/test_cli.py tests/unit/interface/test_adapter.py`
Expected: PASS

### Task 2: Add failing tests for collector batch execution and observability

**Files:**
- Modify: `tests/unit/capabilities/redis_rdb_analysis/collectors/test_path_a_mysql_backed_collector.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_path_a_mysql_backed_collector_batches_using_requested_batch_size():
    assert len(staged_batches) == expected
    assert result.batch_size == requested_size


def test_path_a_mysql_backed_collector_progress_and_metadata_expose_effective_batch_size():
    assert "batch_size=3" in result.progress[0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest -q tests/unit/capabilities/redis_rdb_analysis/collectors/test_path_a_mysql_backed_collector.py`
Expected: FAIL because progress and metadata do not yet include the effective batch-size details.

- [ ] **Step 3: Implement minimal collector changes**

```python
collector = PathAMySQLBackedCollector(
    ...,
    batch_size=request.runtime_inputs.mysql_stage_batch_size,
    mysql_target=mysql_target,
)
```

```python
logger.info(
    "mysql staging batch progress",
    extra={
        "event_name": "mysql_staging_batch_progress",
        "mysql_stage_batch_size": self._batch_size,
        "current_batch_number": batch_number,
        "rows_in_batch": len(batch),
        "cumulative_rows": row_count,
        "elapsed_seconds": ...,
        "mysql_target_host": ...,
        "mysql_target_database": ...,
        "mysql_target_table": table_name,
    },
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest -q tests/unit/capabilities/redis_rdb_analysis/collectors/test_path_a_mysql_backed_collector.py`
Expected: PASS

### Task 3: Add failing tests for approval text and report metadata

**Files:**
- Modify: `tests/unit/orchestrator/test_tools.py`
- Modify: `tests/unit/capabilities/redis_rdb_analysis/test_rdb_analysis_service.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_mysql_staging_approval_message_shows_effective_batch_size(...):
    assert "batch size: 4096" in captured["approval_request"].message


def test_analyze_rdb_mysql_backed_route_metadata_uses_effective_batch_size(...):
    assert result.metadata["mysql_stage_batch_size"] == "4096"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest -q tests/unit/orchestrator/test_tools.py tests/unit/capabilities/redis_rdb_analysis/test_rdb_analysis_service.py`
Expected: FAIL because approval and metadata still rely on the old default flow.

- [ ] **Step 3: Implement minimal orchestrator and service changes**

```python
approval_request = ApprovalRequest(
    ...,
    message=f"... batch size: {batch_size} ...",
    details={"mysql_stage_batch_size": batch_size, ...},
)
```

```python
metadata["mysql_stage_batch_size"] = str(staging.batch_size)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest -q tests/unit/orchestrator/test_tools.py tests/unit/capabilities/redis_rdb_analysis/test_rdb_analysis_service.py`
Expected: PASS

### Task 4: Run focused regression

**Files:**
- Test: `tests/unit/deep_agent_integration/test_config.py`
- Test: `tests/unit/test_cli.py`
- Test: `tests/unit/interface/test_adapter.py`
- Test: `tests/unit/capabilities/redis_rdb_analysis/collectors/test_path_a_mysql_backed_collector.py`
- Test: `tests/unit/orchestrator/test_tools.py`
- Test: `tests/unit/capabilities/redis_rdb_analysis/test_rdb_analysis_service.py`

- [ ] **Step 1: Run the combined regression suite**

Run: `pytest -q tests/unit/deep_agent_integration/test_config.py tests/unit/test_cli.py tests/unit/interface/test_adapter.py tests/unit/capabilities/redis_rdb_analysis/collectors/test_path_a_mysql_backed_collector.py tests/unit/orchestrator/test_tools.py tests/unit/capabilities/redis_rdb_analysis/test_rdb_analysis_service.py`
Expected: PASS

- [ ] **Step 2: Inspect the resulting diff**

Run: `git diff --stat`
Expected: only the planned config, CLI, request-model, collector, orchestrator, and test files changed.
