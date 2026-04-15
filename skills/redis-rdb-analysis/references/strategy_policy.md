# Redis RDB Analysis Strategy Policy

Always inspect local RDB input first with `inspect_local_rdb`. If the file is
missing, stop with the exact missing path.

Small and medium files use direct stream analysis through
`analyze_local_rdb_stream`. Direct stream is the default when files are at most
1 GB.

Files larger than 1 GB should recommend MySQL-backed staging for full analysis.
If the user refuses MySQL, proceed with direct stream after one warning. Do not
repeat negotiation.

Remote Redis RDB acquisition follows:

1. `discover_remote_rdb`
2. `ensure_remote_rdb_snapshot` when fresh snapshot is requested
3. `fetch_remote_rdb_via_ssh`
4. `inspect_local_rdb`
5. selected analysis route

The LLM owns route orchestration. Runtime tools own filesystem checks,
approval-gated actions, streaming execution, and artifact generation.
