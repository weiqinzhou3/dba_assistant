# Redis Inspection Report Writing Guide

Write formal inspection reports as evidence-led documents. Do not guess system
names, topology, hosts, ports, or missing facts.

Use cluster as the primary organization unit. Node-level rows belong inside
cluster sections.

Chapter responsibilities:

- Chapter 1: scope and key inspection counts
- Chapter 2: input evidence and boundaries
- Chapter 3: cluster-level merged issues and remediation priority
- Chapter 4: architecture overview
- Chapter 5-8: method, configuration, OS, and Redis evidence
- Chapter 9: detailed risk items from the same findings
- Appendix: source evidence and grouping audit details

DOCX requests must produce an artifact path. Do not replace a requested artifact
with an inline summary. Keep large wide tables split into smaller topic tables.
