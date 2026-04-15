#!/bin/sh
# Example only. SSH collection must use runtime approval/HITL in production.
# These are read-only examples for operator review.

ssh "$SSH_USER@$SSH_HOST" "tail -n 5000 /var/log/redis/redis.log"
ssh "$SSH_USER@$SSH_HOST" "find /var/log -name '*redis*.log*' -type f -maxdepth 3"
