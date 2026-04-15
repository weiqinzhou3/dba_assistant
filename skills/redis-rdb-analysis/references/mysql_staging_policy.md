# MySQL Staging Policy

Use MySQL-backed staging for RDB files larger than 1 GB when the user accepts
the recommendation. Explain that it improves stability for full key-level
aggregation on large dumps.

If the user refuses MySQL, says no MySQL, direct analysis, or just analyze it,
warn once and continue with direct stream. The refusal path must not loop.

MySQL staging is approval-gated because it writes parsed rows into MySQL. Call
the runtime tool so HITL approval is collected by the harness. Do not ask for
plain-text approval.

Do not invent MySQL host, database, table, credentials, or temporary names. Use
secure runtime context or an approved config collection flow.
