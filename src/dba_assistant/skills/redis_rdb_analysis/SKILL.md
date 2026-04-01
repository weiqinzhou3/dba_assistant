```yaml
skill:
  name: redis-rdb-analysis
  description: Generate Redis RDB analysis outputs from repository-supported collection paths.

status:
  phase_owner: phase-3
  implementation_status: scaffold-only
  execution_status: not-runnable

input_contract:
  required_data:
    - name: source_path
      type: string
      description: Path to one RDB file, an exported analysis data file, or a directory selected by the collector path.
  supported_collectors:
    - offline
    - remote-mysql
  parameters:
    - name: output_mode
      type: string
      default: report
      description: Output mode, either report or summary.
    - name: output_format
      type: string
      default: docx
      description: Report format when output_mode is report.

output_contract:
  analysis_schema: RdbAnalysisResult
  supported_modes:
    - report
    - summary
  supported_formats:
    - docx
    - pdf
    - html
  default_mode: report
  default_format: docx
```

Notes:

- This file defines contract intent only.
- Parsing, SQL workflows, and rendering belong to later phase implementation.
- The skill is intended for later integration into the repository's Deep Agent SDK runtime.
