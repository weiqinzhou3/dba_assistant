# Phase 2: Runtime Assembly & Remote Collection Foundation

## Status

Planning

## Goal

Register skills and tools via Deep Agent SDK, configure the LLM, and implement the remote collection path.

## Tasks

1. Register skills and tools through Deep Agent SDK to complete runtime assembly.
2. Configure a working LLM setup, including model selection, token limits, and retry strategy.
3. Implement Remote Collector infrastructure.
   - `RedisAdaptor`: manage Redis connections, including direct connections and SSH tunnels, and wrap commands such as `INFO`, `CONFIG GET`, `SLOWLOG`, and `CLIENT LIST`.
   - `SSHAdaptor`: manage SSH connections, including remote command execution and file transfer.
   - `MySQLAdaptor`: manage MySQL connections, including query execution and result export.
4. Mark all remote collection paths as read-only. No write operations are executed.
5. Implement PDF Reporter and HTML Reporter if complexity is manageable; otherwise defer them until after Phase 4.

## Acceptance Criteria

- The Agent can invoke registered skills through the SDK.
- At least one remote Adaptor, starting with Redis direct connection, is functional.
- The runtime remains lightweight and does not introduce a custom framework.

## Dependency Notes

- Depends on the shared-layer foundations established in Phase 1.
- Current repository scaffold status is tracked separately in `docs/phases/current-scaffold-status.md`.
