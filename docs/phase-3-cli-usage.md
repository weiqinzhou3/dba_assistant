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
dba-assistant ask "Analyze this RDB and give me a summary" --input /path/to/dump.rdb
dba-assistant ask "按 rcs profile 分析这个 rdb，输出 docx，到 /tmp/rcs.docx" --input /path/to/dump.rdb
dba-assistant ask "分析 redis.example:6379 的最新 rdb，按 rcs profile 输出 summary"
```

## Retained Parameters

The retained flags exist for deterministic local execution and future API / WebUI reuse. They are not the primary UX.

| Flag | Meaning | Notes |
|------|---------|-------|
| `--config` | Load an explicit repository config file. | Overrides the default repository config path. |
| `--input` | Provide one or more local input paths. | Repeatable. Used for local `RDB` files today. |
| `--profile` | Force the analysis profile. | Typical values are `generic` and `rcs`. |
| `--report-format` | Force the rendered output format. | Current public values are `summary` and `docx`. |
| `--output` | Force the output destination. | Required for effective `docx` output. |

## Precedence

The precedence rule is fixed:

1. parse the prompt first
2. derive the normalized request
3. apply explicit CLI overrides second
4. let the unified Deep Agent operate on the final normalized request

That means prompt is the default control surface, but explicit CLI flags still win when both are present.

## What the Unified Agent Sees

The CLI hands the request to the interface adapter, which normalizes it into one shared application request:

- cleaned prompt text
- local input paths
- prompt-derived Redis host / port / db
- extracted secrets such as Redis password
- prompt-derived `profile`, `top_n`, and prefix overrides
- output intent such as `summary` or `docx`

From that point on, the CLI is out of the business-routing path.

The unified Deep Agent then decides whether to use:

- `skills` under `src/dba_assistant/skills/`
- local RDB analysis tools
- live Redis inspection tools
- remote RDB discovery and approval-gated acquisition tools

## Local RDB Examples

### Generic Profile

```sh
dba-assistant ask "Analyze this RDB and focus on key types, expiration, and prefix top 30" \
  --input ./dump.rdb
```

Expected shape:

- prompt expresses the analysis goal
- `--input` supplies the concrete local file
- the unified Deep Agent can select local RDB analysis tools
- the effective profile defaults to `generic`

### `rcs` Profile with DOCX Output

```sh
dba-assistant ask "按 rcs profile 分析这个 rdb，输出 docx，到 /tmp/rcs.docx" \
  --input ./dump.rdb
```

Expected shape:

- prompt selects `rcs`
- prompt requests `docx`
- prompt provides the output path
- the unified Deep Agent selects the local-RDB analysis flow and the generic report renderer

## Remote Redis Example

```sh
dba-assistant ask "分析 redis.example:6379 的最新 rdb，按 rcs profile 输出 summary"
```

Expected shape:

- prompt provides the Redis target
- the unified Deep Agent can choose live Redis inspection tools first
- if it decides to fetch the remote `RDB`, the high-risk tool is protected by Deep Agents `interrupt_on`
- the CLI then asks for approval before the tool call is resumed

The important boundary is this:

- CLI does not reject remote-RDB prompts
- application code does not hard-route remote-RDB prompts away
- approval is a Deep Agent tool-call checkpoint, not a CLI-side business rule

## Current Practical Limits

- Local `.rdb` file paths still come most reliably from `--input`
- The remote-RDB flow currently supports discovery plus approval-gated acquisition intent, but the actual SSH-based file fetch is still scaffold-only
- `precomputed_dataset` remains a Phase 3 route, but the current public CLI does not expose a separate `input-kind` flag for it

## Debugging Principle

If you need exact reproducibility, keep using the prompt plus small explicit overrides:

```sh
dba-assistant ask "按 generic profile 分析这个 rdb，输出 summary" \
  --input ./dump.rdb \
  --profile generic \
  --report-format summary
```

That preserves the prompt-first user shape while still leaving a stable structured boundary for future API and WebUI callers.
