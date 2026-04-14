# Application Layer

This package holds the presentation-neutral application layer for DBA Assistant.

CLI, future GUI surfaces, and future API endpoints should share these modules for:

- raw prompt normalization
- structured runtime input handling
- secret separation
- prompt cleaning before model execution

The package intentionally stays independent from CLI wiring and Deep Agents SDK assembly.

It is not a business-routing layer.

Current scope is intentionally narrow:

- extracting and scrubbing secrets such as Redis / SSH / MySQL passwords
- preserving explicit surface inputs that came from CLI / API / Web adapters
- scrubbing secrets from prompt text before model execution
- preserving a shared normalized request contract for every interface

It should not infer connection targets, report strategy, profile choice, route selection, or other analysis policy from free-form natural language.

Non-sensitive runtime parameters such as Redis host/port, SSH host/username, MySQL host/user/database, remote paths, and output paths now belong to agent-facing tool arguments or explicit interface fields, not prompt parsing.
