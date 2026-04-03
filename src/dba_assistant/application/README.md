# Application Layer

This package holds the presentation-neutral application layer for DBA Assistant.

CLI, future GUI surfaces, and future API endpoints should share these modules for:

- raw prompt normalization
- structured runtime input handling
- secret separation
- prompt cleaning before model execution

The package intentionally stays independent from CLI wiring and Deep Agents SDK assembly.
