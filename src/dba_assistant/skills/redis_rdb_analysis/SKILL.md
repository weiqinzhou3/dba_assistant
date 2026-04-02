```yaml
skill:
  name: redis-rdb-analysis
  description: Define Redis RDB analysis contracts and package scaffolding for later Phase 3 implementation.

status:
  phase_owner: phase-3
  implementation_status: contract-groundwork
  execution_status: not-invokable-yet

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

- This file defines Task 1 contract intent only.
- Parsing, SQL workflows, rendering, and runtime wiring belong to later Phase 3 implementation.
- The skill is not invokable yet; it only reserves the package and shared contract surface.
