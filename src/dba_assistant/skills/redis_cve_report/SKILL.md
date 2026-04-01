```yaml
skill:
  name: redis-cve-report
  description: Generate Redis CVE intelligence outputs from online or offline data sources.

status:
  phase_owner: phase-6
  implementation_status: scaffold-only
  execution_status: not-runnable

input_contract:
  required_data:
    - name: time_range
      type: string
      description: Natural language or explicit time range for the CVE search window.
  supported_collectors:
    - offline
    - online-fetch
  parameters:
    - name: redis_version_range
      type: string
      default: ""
      description: Optional Redis version range for later impact assessment.
    - name: output_mode
      type: string
      default: report
      description: Output mode, either report or summary.
    - name: output_format
      type: string
      default: docx
      description: Report format when output_mode is report.

output_contract:
  analysis_schema: RedisCveAnalysisResult
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
- Fetching, deduplication, and impact assessment belong to later phase implementation.
- The skill is intended for later integration into the repository's Deep Agent SDK runtime.
