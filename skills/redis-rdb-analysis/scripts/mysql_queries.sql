-- Example only. Production execution is handled by repository tools.
-- Read-only inspection queries for MySQL staging tables.

SELECT redis_type, COUNT(*) AS key_count, SUM(memory_bytes) AS memory_bytes
FROM staging_table
GROUP BY redis_type
ORDER BY memory_bytes DESC
LIMIT 50;

SELECT key_name, redis_type, memory_bytes
FROM staging_table
ORDER BY memory_bytes DESC
LIMIT 100;

SELECT SUBSTRING_INDEX(key_name, ':', 1) AS prefix, COUNT(*) AS key_count
FROM staging_table
GROUP BY prefix
ORDER BY key_count DESC
LIMIT 100;
