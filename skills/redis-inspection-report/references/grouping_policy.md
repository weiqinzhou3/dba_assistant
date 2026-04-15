# Redis Inspection Grouping Policy

Redis inspection reports use the cluster as the minimum reporting unit. Do not guess
system or cluster ownership from weak evidence. When grouping evidence is
missing, keep the node in an unresolved cluster and state that the evidence is
insufficient.

Use these inputs for grouping when present:

- Redis Cluster node IDs and slot ownership
- replication master/replica relationships
- explicit hostnames, ports, and source paths
- shared evidence bundle naming only as weak supporting evidence

Chapter 3 is the cluster-level problem overview. It merges findings for the same
cluster by `merge_key` first, then by issue name, severity, impact, and
recommendation. The affected node column should aggregate all involved nodes.

Chapter 9 is the detailed risk section. It uses the same reviewed issue set as
Chapter 3, but keeps full evidence and recommendations. It must not rerun a
separate log anomaly rule.
