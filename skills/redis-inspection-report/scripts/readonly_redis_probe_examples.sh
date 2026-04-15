#!/bin/sh
# Example only. Production probing is implemented by repository tools.
# All commands are readonly / read-only.

redis-cli -h "$REDIS_HOST" -p "${REDIS_PORT:-6379}" PING
redis-cli -h "$REDIS_HOST" -p "${REDIS_PORT:-6379}" INFO
redis-cli -h "$REDIS_HOST" -p "${REDIS_PORT:-6379}" CONFIG GET '*'
redis-cli -h "$REDIS_HOST" -p "${REDIS_PORT:-6379}" SLOWLOG GET 128
redis-cli -h "$REDIS_HOST" -p "${REDIS_PORT:-6379}" CLUSTER INFO
redis-cli -h "$REDIS_HOST" -p "${REDIS_PORT:-6379}" CLUSTER NODES
