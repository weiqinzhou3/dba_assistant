from dba_assistant.adaptors.redis_adaptor import RedisConnectionConfig
from dba_assistant.skills.redis_rdb_analysis.remote_input import discover_remote_rdb


class FakeRedisAdaptor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    def info(self, connection: RedisConnectionConfig, *, section: str | None = None) -> dict[str, object]:
        self.calls.append(("info", section))
        return {"rdb_last_save_time": 1710000000, "rdb_bgsave_in_progress": 0}

    def config_get(self, connection: RedisConnectionConfig, *, pattern: str) -> dict[str, object]:
        self.calls.append(("config_get", pattern))
        if pattern == "dir":
            return {"available": True, "pattern": pattern, "data": {"dir": "/data/redis"}}
        if pattern == "dbfilename":
            return {"available": True, "pattern": pattern, "data": {"dbfilename": "dump.rdb"}}
        raise AssertionError(f"unexpected pattern: {pattern}")


def test_discover_remote_rdb_reports_path_and_requires_confirmation() -> None:
    adaptor = FakeRedisAdaptor()
    connection = RedisConnectionConfig(host="redis.example", port=6379)

    discovery = discover_remote_rdb(adaptor, connection)

    assert discovery == {
        "lastsave": 1710000000,
        "bgsave_in_progress": 0,
        "rdb_path": "/data/redis/dump.rdb",
        "requires_confirmation": True,
    }
    assert adaptor.calls == [
        ("info", "persistence"),
        ("config_get", "dir"),
        ("config_get", "dbfilename"),
    ]
