# Strict Harness Tool Parameterization Design

## Scope

This design tightens DBA Assistant further toward strict Harness Engineering.

The target is no longer "prompt-first with some hard-fact parsing." The target is:

- boundary/application keeps only security-oriented prompt sanitization and explicit surface-field merging
- the LLM owns natural-language understanding and non-sensitive parameter selection
- agent-facing tools accept explicit non-sensitive parameters instead of relying on pre-normalized connection context
- secrets stay outside the model and outside tool signatures

## Problem Statement

The current runtime still carries a hidden non-Harness assumption:

- `application/prompt_parser.py` extracts Redis / SSH / MySQL host and mode signals from free-form prompt text
- `build_all_tools(...)` builds closures around request-derived connections
- several tools remain composite and depend on request context rather than explicit tool arguments

This keeps Python in the loop for connection understanding and execution routing.

## Goal

Preserve the unified execution path:

`CLI / API / WebUI -> interface adapter -> one Deep Agent -> skills/tools`

while making the boundaries stricter:

- `application/` strips secrets and merges explicit interface fields only
- agent-facing tools expose business actions with explicit non-sensitive arguments
- runtime injects secrets and approval, but not language understanding
- remote acquisition becomes a sequence of smaller business tools instead of a single composite fetch-and-analyze tool

## Boundary Decisions

### 1. `application/` responsibilities

Keep:

- request dataclasses
- password extraction and prompt scrubbing
- explicit interface override merging
- output contract defaults that come from interface/config, not from prompt prose

Remove from prompt parsing:

- Redis host/port extraction from prose
- SSH host/user extraction from prose
- MySQL host/user/database extraction from prose
- remote acquisition mode inference from prose
- prompt-derived DOCX/report path inference
- broad route inference from prose

### 2. Tool registration

All agent-facing business tools should be registered regardless of whether request normalization found connection info.

Tools are not filtered by prebuilt Redis/MySQL connections anymore. Instead, each tool resolves its own runtime connection from:

1. explicit tool arguments
2. explicit interface-level overrides already stored on the request
3. secure secrets held by the runtime

### 3. Secrets handling

Secrets remain outside the model and outside tool signatures.

Allowed:

- `request.secrets.redis_password`
- `request.secrets.ssh_password`
- `request.secrets.mysql_password`
- `ask_user_for_config(..., secure=True)` when a required secret is missing

Disallowed:

- tool parameters like `ssh_password`
- prompt-parser growth that tries to understand whole SSH/MySQL connection grammar

### 4. Tool shape

Agent-facing tools stay business-oriented, not protocol-oriented.

Allowed examples:

- `redis_ping(redis_host, redis_port=6379, redis_db=0)`
- `discover_remote_rdb(redis_host, redis_port=6379, redis_db=0, remote_rdb_path="")`
- `ensure_remote_rdb_snapshot(redis_host, redis_port=6379, redis_db=0)`
- `fetch_remote_rdb_via_ssh(remote_rdb_path, ssh_host, ssh_port=22, ssh_username="")`
- `stage_local_rdb_to_mysql(input_paths, mysql_host, mysql_port=3306, mysql_user="", mysql_database="", mysql_table="")`
- `analyze_staged_rdb(mysql_table, mysql_host="", mysql_port=3306, mysql_user="", mysql_database="", ...)`

Disallowed examples:

- generic `ssh(...)`
- generic `scp(...)`
- tools whose primary behavior depends on hidden request-derived connection state

### 5. Remote acquisition flow

Remote Redis analysis should become an explicit tool chain:

1. `discover_remote_rdb`
2. `ensure_remote_rdb_snapshot` when latest snapshot is required
3. `fetch_remote_rdb_via_ssh`
4. `inspect_local_rdb`
5. `analyze_local_rdb_stream` or `stage_local_rdb_to_mysql`

This removes the current composite fetch-and-analyze behavior.

### 6. Approval model

Sensitive remote and write actions must be runtime-gated with `interrupt_on`.

Approval-gated actions:

- `ensure_remote_rdb_snapshot`
- `fetch_remote_rdb_via_ssh`
- MySQL write/staging tools

Read-only tools remain ungated.

## Execution Strategy

1. Replace prompt-parser overreach with secret-only sanitization plus explicit interface fields.
2. Introduce tool-runtime helpers that resolve Redis, SSH, and MySQL configs from explicit tool args plus secure context.
3. Refactor each agent-facing tool to accept explicit non-sensitive parameters.
4. Split remote acquisition into discover / ensure snapshot / fetch / analyze steps.
5. Remove request-derived connection gating from tool registration and agent assembly.
6. Update prompts, skills, and tests to reflect the new flow.

## Acceptance Criteria

The refactor is complete when all of the following are true:

- `normalize_raw_request(...)` no longer extracts Redis / SSH / MySQL connection endpoints from free-form prompt text
- passwords are still scrubbed from prompt text and retained in secure request secrets
- `build_all_tools(...)` does not require prebuilt Redis or MySQL connections
- agent-facing Redis/MySQL/remote-RDB tools accept explicit non-sensitive parameters
- `fetch_remote_rdb_via_ssh` only fetches; it does not auto-discover and auto-analyze in one step
- `ensure_remote_rdb_snapshot` is agent-facing and approval-gated
- runtime approval policy is enforced for all sensitive remote/write operations
- local and remote analysis flows still pass repository verification
