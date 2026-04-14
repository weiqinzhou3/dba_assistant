# Phase 3 CLI Usage

Phase 3 is `prompt-first`, but the CLI is intentionally thin.

The public surface is:

```sh
dba-assistant ask "<prompt>"
```

The CLI does not decide which phase path, skill, or tool should run. It only:

1. accepts the prompt
2. accepts a small set of optional structured overrides
3. forwards one normalized request into the shared interface adapter
4. lets the unified Deep Agent choose `skills` and `tools`

The target architecture is:

`CLI / API / WebUI -> interface adapter -> one Deep Agent -> skills/tools`

## Primary Command

```sh
dba-assistant ask "<prompt>"
```

Examples:

```sh
dba-assistant ask "分析 /data/dump.rdb，重点看 TTL 和大 key"
dba-assistant ask "分析 /data/a.rdb 和 /data/b.rdb，按 rcs profile 输出 docx，到 /tmp/rcs.docx"
dba-assistant ask "分析 redis.example:6379 的最新 rdb，按 rcs profile 输出 summary"
dba-assistant ask "从 MySQL 192.168.0.10:3306，用户名 root，密码 secret123，数据库 dba，表 redis_rows 读取预处理数据并分析"
```

## Retained Parameters

The retained flags exist for deterministic local execution, debugging, and future API / WebUI reuse. They are not the primary UX.

| Flag | Meaning | Notes |
|------|---------|-------|
| `--config` | Load an explicit repository config file. | Overrides the default repository config path. |
| `--input` | Provide one or more local input paths. | Repeatable explicit surface input when exact reproduction is needed. |
| `--input-kind` | Force the input source category. | Use only as an explicit override. |
| `--path-mode` | Force the canonical route name. | Canonical values are `database_backed_analysis`, `preparsed_dataset_analysis`, and `direct_rdb_analysis`. |
| `--profile` | Force the analysis profile. | Typical values are `generic` and `rcs`. |
| `--report-format` | Force the rendered output format. | Current public values are `summary` and `docx`. |
| `--output` | Force the output destination. | Required for effective `docx` output. |
| `--mysql-host` / `--mysql-port` / `--mysql-user` / `--mysql-password` / `--mysql-database` | Provide MySQL connection context. | Explicit structured surface fields that override any runtime defaults. |
| `--mysql-table` / `--mysql-query` | Point to a MySQL-backed preparsed dataset. | Explicit structured surface fields. |

## Precedence

The precedence rule is fixed:

1. normalize and scrub the prompt for secrets
2. preserve explicit interface fields
3. apply explicit CLI overrides
4. let the unified Deep Agent operate on the final normalized request

That means prompt is the default control surface, but explicit CLI flags still win when both are present.

## What the Unified Agent Sees

The CLI hands the request to the interface adapter, which normalizes it into one shared application request:

- cleaned prompt text
- explicit local input paths when present
- extracted secrets such as Redis, SSH, or MySQL password
- bounded interface overrides such as `--profile`, `--report-format`, and `--path-mode`

From that point on, the CLI is out of the business-routing path.

The unified Deep Agent then decides whether to use:

- `skills` under repository-root `skills/`
- local RDB analysis tools
- live Redis inspection tools
- remote RDB discovery and approval-gated acquisition tools

## Local RDB Examples

### Generic Profile

```sh
dba-assistant ask "Analyze ./dump.rdb and focus on key types, expiration, and prefix top 30"
```

Expected shape:

- prompt expresses the analysis goal
- prompt supplies the concrete local file
- the unified Deep Agent can select local RDB analysis tools
- the effective profile defaults to `generic`

### Multiple Local RDB Files

```sh
dba-assistant ask "分析 /data/a.rdb 和 /data/b.rdb，重点看 TTL、过期分布和大 key"
```

Expected shape:

- the interface adapter extracts both local file paths into `input_paths`
- the shared contract still carries a structured tuple of paths
- explicit `--input` remains available only if the caller needs an override or exact replay

### `rcs` Profile with DOCX Output

```sh
dba-assistant ask "按 rcs profile 分析 ./dump.rdb，输出 docx，到 /tmp/rcs.docx"
```

Expected shape:

- the prompt states the desired profile and asks for a document in natural language
- the interface adapter extracts the explicit `.docx` output path and local `.rdb` path
- the unified Deep Agent decides whether to pass `profile_name='rcs'` and `report_format='docx'` into the selected tools
- if DOCX is selected, runtime must return a real `.docx` artifact path instead of terminal-only text

## MySQL Preparsed Dataset Example

```sh
dba-assistant ask "从 MySQL 192.168.0.10:3306，用户名 root，密码 secret123，数据库 dba，表 redis_rows 读取预处理数据并分析"
```

Expected shape:

- prompt supplies the MySQL host, credentials, database, and table
- the interface adapter writes those values into the shared request contract
- the normalized request infers `input_kind=preparsed_mysql` from those explicit fields
- the unified agent or analysis layer can enter `preparsed_dataset_analysis` without CLI-specific branching

## Remote Redis Example

```sh
dba-assistant ask "分析 redis.example:6379 的最新 rdb，按 rcs profile 输出 summary"
```

Expected shape:

- prompt provides the Redis target
- the unified Deep Agent can choose live Redis inspection tools first
- if it decides to fetch a remote `RDB` or stage a large local `RDB` into MySQL, the high-risk tool is protected by Deep Agents `interrupt_on`
- the CLI then asks for approval before the tool call is resumed

The important boundary is this:

- CLI does not reject remote-RDB prompts
- application code does not hard-route remote-RDB prompts away
- approval is a Deep Agent tool-call checkpoint, not a CLI-side business rule

## Current Practical Limits

- Prompt extraction is intentionally narrow: secrets are scrubbed before model execution, while non-sensitive connection targets and paths should flow through explicit interface fields or LLM-selected tool arguments
- Free-form profile choice, route choice, and analysis policy are left to the LLM unless the caller supplies explicit flags
- Explicit flags remain the fallback for exact reproducibility, debugging, or when a caller wants to override derived or default runtime values
- Remote RDB acquisition now stays inside the unified agent flow, but SSH credential policy is still intentionally narrow

## Debugging Principle

If you need exact reproducibility, keep using the prompt plus small explicit overrides:

```sh
dba-assistant ask "按 generic profile 分析这个 rdb，输出 summary" \
  --input ./dump.rdb \
  --profile generic \
  --report-format summary
```

That keeps prompt as the main UX while still leaving a stable structured boundary and deterministic override layer for future API and WebUI callers.
