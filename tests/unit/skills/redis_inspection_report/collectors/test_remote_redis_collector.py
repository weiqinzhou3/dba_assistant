from dba_assistant.adaptors.redis_adaptor import RedisConnectionConfig
from dba_assistant.skills.redis_inspection_report.collectors.remote_redis_collector import (
    RedisInspectionRemoteCollector,
    RedisInspectionRemoteInput,
)


class FakeRedisAdaptor:
    def ping(self, connection: RedisConnectionConfig):
        return {"ok": True, "host": connection.host}

    def info(self, connection: RedisConnectionConfig, section=None):
        return {"role": "master", "section": section}

    def config_get(self, connection: RedisConnectionConfig, pattern="*"):
        return {"pattern": pattern}

    def slowlog_get(self, connection: RedisConnectionConfig, length=10):
        return [{"length": length}]

    def client_list(self, connection: RedisConnectionConfig):
        return [{"addr": "127.0.0.1:5000"}]


def test_remote_redis_collector_reads_structured_redis_snapshot() -> None:
    collector = RedisInspectionRemoteCollector(adaptor=FakeRedisAdaptor())
    result = collector.collect(
        RedisInspectionRemoteInput(
            connection=RedisConnectionConfig(host="redis.example"),
            info_section="server",
            config_pattern="max*",
            slowlog_length=5,
        )
    )

    assert result["ping"]["host"] == "redis.example"
    assert result["info"]["section"] == "server"
    assert result["config"]["pattern"] == "max*"
    assert result["slowlog"][0]["length"] == 5
