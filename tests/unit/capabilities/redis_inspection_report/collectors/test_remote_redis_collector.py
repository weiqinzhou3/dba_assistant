import pytest

from dba_assistant.adaptors.redis_adaptor import RedisConnectionConfig
from dba_assistant.capabilities.redis_inspection_report.collectors.remote_redis_collector import (
    RedisInspectionRemoteCollector,
    RedisInspectionRemoteInput,
)


class FakeRedisAdaptor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def ping(self, connection: RedisConnectionConfig):
        return {"ok": True, "host": connection.host}

    def info(self, connection: RedisConnectionConfig, section=None):
        return {"role": "master", "section": section}

    def config_get(self, connection: RedisConnectionConfig, pattern="maxmemory*"):
        self.calls.append(("config", pattern))
        return {"available": True, "pattern": pattern, "data": {"maxmemory": "0"}}

    def slowlog_get(self, connection: RedisConnectionConfig, length=5):
        self.calls.append(("slowlog", length))
        return {
            "available": True,
            "requested_length": length,
            "count": 1,
            "entries": [{"id": 1, "duration": 99, "command": "SET"}],
        }

    def client_list(self, connection: RedisConnectionConfig):
        return {"available": True, "count": 1}

    def cluster_info(self, connection: RedisConnectionConfig):
        return {"available": True, "data": {"cluster_state": "ok", "cluster_known_nodes": "2"}}

    def cluster_nodes(self, connection: RedisConnectionConfig):
        return {
            "available": True,
            "nodes": [
                {
                    "node_id": "node-a",
                    "ip": connection.host,
                    "port": connection.port,
                    "role": "master",
                }
            ],
        }


class LimitedRedisAdaptor(FakeRedisAdaptor):
    def config_get(self, connection: RedisConnectionConfig, pattern="maxmemory*"):
        return {
            "available": False,
            "pattern": pattern,
            "error": {"kind": "permission_denied", "message": "NOPERM"},
        }

    def slowlog_get(self, connection: RedisConnectionConfig, length=5):
        return {
            "available": False,
            "requested_length": length,
            "error": {"kind": "command_unavailable", "message": "unknown command"},
        }

    def client_list(self, connection: RedisConnectionConfig):
        return {
            "available": False,
            "error": {"kind": "permission_denied", "message": "NOPERM"},
        }

    def cluster_info(self, connection: RedisConnectionConfig):
        return {
            "available": False,
            "error": {"kind": "command_unavailable", "message": "cluster support disabled"},
        }

    def cluster_nodes(self, connection: RedisConnectionConfig):
        return {
            "available": False,
            "error": {"kind": "command_unavailable", "message": "cluster support disabled"},
        }


def test_remote_redis_collector_reads_structured_redis_snapshot() -> None:
    adaptor = FakeRedisAdaptor()
    collector = RedisInspectionRemoteCollector(adaptor=adaptor)
    result = collector.collect(
        RedisInspectionRemoteInput(
            connection=RedisConnectionConfig(host="redis.example"),
            info_section="server",
            config_pattern="maxmemory*",
            slowlog_length=5,
        )
    )

    assert result["ping"]["host"] == "redis.example"
    assert result["info"]["section"] == "server"
    assert result["config"] == {
        "available": True,
        "pattern": "maxmemory*",
        "data": {"maxmemory": "0"},
    }
    assert result["slowlog"] == {
        "available": True,
        "requested_length": 5,
        "count": 1,
        "entries": [{"id": 1, "duration": 99, "command": "SET"}],
    }
    assert result["clients"] == {"available": True, "count": 1}
    assert result["cluster_info"] == {
        "available": True,
        "data": {"cluster_state": "ok", "cluster_known_nodes": "2"},
    }
    assert result["cluster_nodes"]["nodes"][0]["node_id"] == "node-a"
    assert adaptor.calls == [("config", "maxmemory*"), ("slowlog", 5)]


def test_remote_redis_collector_keeps_admin_probe_failures_structured() -> None:
    collector = RedisInspectionRemoteCollector(adaptor=LimitedRedisAdaptor())

    result = collector.collect(RedisInspectionRemoteInput(connection=RedisConnectionConfig(host="redis.example")))

    assert result["config"]["available"] is False
    assert result["config"]["error"]["kind"] == "permission_denied"
    assert result["slowlog"]["available"] is False
    assert result["slowlog"]["error"]["kind"] == "command_unavailable"
    assert result["clients"]["available"] is False
    assert result["clients"]["error"]["kind"] == "permission_denied"
    assert result["cluster_info"]["available"] is False
    assert result["cluster_info"]["error"]["kind"] == "command_unavailable"
    assert result["cluster_nodes"]["available"] is False
    assert result["cluster_nodes"]["error"]["kind"] == "command_unavailable"


def test_remote_redis_collector_rejects_broad_config_patterns() -> None:
    with pytest.raises(ValueError, match="config_pattern"):
        RedisInspectionRemoteInput(
            connection=RedisConnectionConfig(host="redis.example"),
            config_pattern="*",
        )


def test_remote_redis_collector_rejects_large_slowlog_requests() -> None:
    with pytest.raises(ValueError, match="slowlog_length"):
        RedisInspectionRemoteInput(
            connection=RedisConnectionConfig(host="redis.example"),
            slowlog_length=6,
        )
