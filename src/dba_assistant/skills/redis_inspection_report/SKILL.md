```yaml
skill:
  name: redis-inspection-report
  description: Generate Redis inspection report outputs from offline or remote collection paths.

status:
  phase_owner: phase-4
  implementation_status: scaffold-only
  execution_status: not-runnable

input_contract:
  required_data:
    - name: source_path
      type: string
      description: Path to an inspection bundle directory or remote target selected by the collector path.
  supported_collectors:
    - offline
    - remote-redis
    - remote-ssh
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
  analysis_schema: InspectionAnalysisResult
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
- Collection, normalization, analysis, and rendering belong to later phase implementation.
- The skill is intended for later integration into the repository's Deep Agent SDK runtime.
