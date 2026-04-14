# redis-inspection-report Collectors

This directory contains collector implementations for Redis inspection data paths.

Current coverage:

- Offline evidence directories and `.tar.gz` bundles are normalized into the shared inspection dataset.
- Live Redis collection remains read-only and gathers bounded INFO, CONFIG, SLOWLOG, CLIENT LIST, and CLUSTER probes.
