# Redis Log Judgement Guide

The program collects log candidates; the LLM performs semantic judgement.

Normal AOF examples:

- Background append only file rewriting terminated with success
- AOF rewrite completed successfully

Normal RDB examples:

- RDB: N MB of memory used by copy-on-write
- Background saving terminated with success
- RDB copy-on-write memory statistics after a successful background save

These normal AOF/RDB persistence messages are operating evidence, not anomalies
by themselves.

True anomalous examples include:

- OOM command not allowed
- fork operation failed or cannot allocate memory
- master link down, replication break, or repeated full resync failures
- cluster fail state or slots not covered
- warning messages that describe data loss, failed persistence, or unavailable service

The LLM should decide whether a candidate is anomalous, explain why, assign log
severity, choose a merge_key, aggregate affected nodes, and write a
recommendation. It should mark routine noise as `is_anomalous=false`.
